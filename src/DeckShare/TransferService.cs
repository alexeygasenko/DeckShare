using System.Collections.Concurrent;
using System.Diagnostics;
using System.IO;
using System.Security.Cryptography;
using Renci.SshNet;
using Renci.SshNet.Common;

namespace DeckShare;

public sealed class TransferService
{
    private readonly AppSettings _settings;
    private readonly string _secret;
    private readonly string _language;
    private readonly Action<string, string> _log;
    private readonly Action<ProgressUpdate> _progress;
    private readonly Action<string> _completeProgress;
    private readonly Action<string> _removeProgress;
    private readonly ProgressTracker _tracker = new();

    public TransferService(
        AppSettings settings,
        string secret,
        Action<string, string> log,
        Action<ProgressUpdate> progress,
        Action<string> completeProgress,
        Action<string> removeProgress)
    {
        _settings = settings;
        _secret = secret;
        _language = settings.Language;
        _log = log;
        _progress = progress;
        _completeProgress = completeProgress;
        _removeProgress = removeProgress;
    }

    public async Task TestConnectionAsync(CancellationToken cancellationToken)
    {
        await Task.Run(() =>
        {
            cancellationToken.ThrowIfCancellationRequested();
            Log("info", "connecting", _settings.Username, _settings.Host, _settings.Port);
            using var client = CreateSftpClient();
            client.Connect();
            cancellationToken.ThrowIfCancellationRequested();
            client.Disconnect();
            Log("success", "connectionOk");
        }, cancellationToken);
    }

    public async Task TransferAsync(CancellationToken cancellationToken)
    {
        var (tasks, skipped) = await Task.Run(() => BuildTasks(cancellationToken), cancellationToken);
        _tracker.Start(tasks.Sum(task => task.Size));
        var uploaded = 0;
        var options = new ParallelOptions
        {
            CancellationToken = cancellationToken,
            MaxDegreeOfParallelism = Math.Clamp(_settings.ParallelTransfers, 1, 8)
        };

        await Parallel.ForEachAsync(tasks, options, async (task, token) =>
        {
            await UploadAsync(task, token);
            Interlocked.Increment(ref uploaded);
        });

        Log("success", "complete", uploaded, skipped);
    }

    private (List<UploadTask> Tasks, int Skipped) BuildTasks(CancellationToken cancellationToken)
    {
        var tasks = new List<UploadTask>();
        var skipped = 0;
        Log("info", "connecting", _settings.Username, _settings.Host, _settings.Port);
        using var client = CreateSftpClient();
        client.Connect();

        foreach (var source in _settings.Sources)
        {
            cancellationToken.ThrowIfCancellationRequested();
            if (!Directory.Exists(source.LocalPath)) throw new DirectoryNotFoundException(T("missingFolder", source.LocalPath));
            var remoteRoot = NormalizeRemotePath(source.RemotePath);
            EnsureRemoteDirectory(client, remoteRoot);
            Log("info", "processing", source.LocalPath);

            foreach (var localFile in Directory.EnumerateFiles(source.LocalPath, "*", SearchOption.AllDirectories))
            {
                cancellationToken.ThrowIfCancellationRequested();
                var relative = Path.GetRelativePath(source.LocalPath, localFile).Replace('\\', '/');
                var remoteFile = CombineRemote(remoteRoot, relative);
                var remoteDirectory = RemoteDirectory(remoteFile);
                EnsureRemoteDirectory(client, remoteDirectory);
                var size = new FileInfo(localFile).Length;

                if (client.Exists(remoteFile) && client.GetAttributes(remoteFile).Size == size)
                {
                    skipped++;
                    Log("output", "skipped", remoteFile);
                    continue;
                }

                tasks.Add(new UploadTask(
                    Guid.NewGuid().ToString("N"),
                    localFile,
                    remoteFile,
                    remoteFile + ".deckshare-part",
                    size));
            }
        }

        client.Disconnect();
        return (tasks, skipped);
    }

    private async ValueTask UploadAsync(UploadTask task, CancellationToken cancellationToken)
    {
        await Task.Run(() =>
        {
            var started = Stopwatch.StartNew();
            using var sftp = CreateSftpClient();
            using var ssh = CreateSshClient();
            sftp.Connect();
            ssh.Connect();
            RemoveIfExists(sftp, task.TempPath);

            try
            {
                Report(task, 0, started.Elapsed);
                using (var input = File.OpenRead(task.LocalPath))
                {
                    sftp.UploadFile(input, task.TempPath, true, sent =>
                    {
                        cancellationToken.ThrowIfCancellationRequested();
                        Report(task, checked((long)sent), started.Elapsed);
                    });
                }

                cancellationToken.ThrowIfCancellationRequested();
                Log("output", "verifying", task.TempPath);
                using var hashInput = File.OpenRead(task.LocalPath);
                var localHash = Convert.ToHexString(SHA256.HashData(hashInput)).ToLowerInvariant();
                cancellationToken.ThrowIfCancellationRequested();
                var remoteHash = RunChecked(ssh, $"sha256sum -- {Quote(task.TempPath)}").Split(' ', StringSplitOptions.RemoveEmptyEntries)[0];
                var remoteSize = sftp.GetAttributes(task.TempPath).Size;
                if (remoteSize != task.Size || !string.Equals(localHash, remoteHash, StringComparison.OrdinalIgnoreCase))
                {
                    throw new InvalidDataException($"SHA-256 verification failed: {task.RemotePath}");
                }

                cancellationToken.ThrowIfCancellationRequested();
                RunChecked(ssh, $"mv -f -- {Quote(task.TempPath)} {Quote(task.RemotePath)}");
                _tracker.Complete(task.Id, task.Size);
                _completeProgress(task.Id);
                Log("output", "uploaded", task.RemotePath, FormatSpeed(task.Size / Math.Max(started.Elapsed.TotalSeconds, 0.001)));
            }
            catch
            {
                try { RemoveIfExists(sftp, task.TempPath); } catch { }
                _tracker.Remove(task.Id);
                _removeProgress(task.Id);
                throw;
            }
            finally
            {
                if (sftp.IsConnected) sftp.Disconnect();
                if (ssh.IsConnected) ssh.Disconnect();
            }
        }, cancellationToken);
    }

    private void Report(UploadTask task, long sent, TimeSpan elapsed)
    {
        var seconds = Math.Max(elapsed.TotalSeconds, 0.001);
        var speed = sent / seconds;
        var total = _tracker.Update(task.Id, sent);
        var fileEta = speed > 0 ? (task.Size - sent) / speed : double.NaN;
        _progress(new ProgressUpdate(
            task.Id,
            Path.GetFileName(task.LocalPath),
            RemoteDirectory(task.RemotePath),
            FormatSpeed(speed),
            FormatPercent(sent, task.Size),
            FormatDuration(fileEta),
            total.Eta,
            total.Speed));
    }

    private SftpClient CreateSftpClient() => new(CreateConnectionInfo());
    private SshClient CreateSshClient() => new(CreateConnectionInfo());

    private ConnectionInfo CreateConnectionInfo()
    {
        AuthenticationMethod authentication;
        if (_settings.AuthMethod == "key")
        {
            var key = string.IsNullOrEmpty(_secret)
                ? new PrivateKeyFile(_settings.IdentityFile)
                : new PrivateKeyFile(_settings.IdentityFile, _secret);
            authentication = new PrivateKeyAuthenticationMethod(_settings.Username, key);
        }
        else
        {
            authentication = new PasswordAuthenticationMethod(_settings.Username, _secret);
        }

        return new ConnectionInfo(_settings.Host, _settings.Port, _settings.Username, authentication)
        {
            Timeout = TimeSpan.FromSeconds(15)
        };
    }

    private static void EnsureRemoteDirectory(SftpClient client, string path)
    {
        var current = "";
        foreach (var part in NormalizeRemotePath(path).Split('/', StringSplitOptions.RemoveEmptyEntries))
        {
            current += "/" + part;
            if (!client.Exists(current)) client.CreateDirectory(current);
        }
    }

    private static void RemoveIfExists(SftpClient client, string path)
    {
        if (client.Exists(path)) client.DeleteFile(path);
    }

    private static string RunChecked(SshClient client, string command)
    {
        var result = client.RunCommand(command);
        if (result.ExitStatus != 0) throw new SshException(string.IsNullOrWhiteSpace(result.Error) ? command : result.Error.Trim());
        return result.Result.Trim();
    }

    private static string NormalizeRemotePath(string value)
    {
        var normalized = "/" + string.Join('/', value.Replace('\\', '/').Split('/', StringSplitOptions.RemoveEmptyEntries));
        return normalized == "" ? "/" : normalized;
    }

    private static string CombineRemote(string root, string relative) =>
        NormalizeRemotePath(root.TrimEnd('/') + "/" + relative.TrimStart('/'));

    private static string RemoteDirectory(string path)
    {
        var index = path.LastIndexOf('/');
        return index <= 0 ? "/" : path[..index];
    }

    private static string Quote(string value) => "'" + value.Replace("'", "'\"'\"'") + "'";

    private string T(string key, params object[] args) => Localization.Get(_language, key, args);
    private void Log(string level, string key, params object[] args) => _log(level, T(key, args));

    public static string FormatSpeed(double bytesPerSecond)
    {
        string[] units = ["B/s", "KB/s", "MB/s", "GB/s"];
        var value = Math.Max(bytesPerSecond, 0);
        var unit = 0;
        while (value >= 1024 && unit < units.Length - 1)
        {
            value /= 1024;
            unit++;
        }
        return unit == 0 ? $"{value:0} {units[unit]}" : $"{value:0.0} {units[unit]}";
    }

    public static string FormatDuration(double seconds)
    {
        if (double.IsNaN(seconds) || double.IsInfinity(seconds) || seconds < 0) return "--";
        var duration = TimeSpan.FromSeconds(Math.Round(seconds));
        return duration.TotalHours >= 1 ? $"{(int)duration.TotalHours}:{duration.Minutes:00}:{duration.Seconds:00}" : $"{duration.Minutes}:{duration.Seconds:00}";
    }

    private static string FormatPercent(long sent, long total) => total <= 0 ? "100.0%" : $"{Math.Min(sent * 100d / total, 100):0.0}%";

    private sealed class ProgressTracker
    {
        private readonly object _sync = new();
        private readonly ConcurrentDictionary<string, long> _active = new();
        private long _completed;
        private long _total;
        private Stopwatch _watch = new();

        public void Start(long total)
        {
            _total = total;
            _completed = 0;
            _active.Clear();
            _watch = Stopwatch.StartNew();
        }

        public (string Eta, string Speed) Update(string id, long bytes)
        {
            _active[id] = bytes;
            lock (_sync)
            {
                var sent = _completed + _active.Values.Sum();
                var speed = sent / Math.Max(_watch.Elapsed.TotalSeconds, 0.001);
                return (
                    FormatDuration(speed > 0 ? Math.Max(_total - sent, 0) / speed : double.NaN),
                    FormatSpeed(speed));
            }
        }

        public void Complete(string id, long size)
        {
            lock (_sync)
            {
                _active.TryRemove(id, out _);
                _completed += size;
            }
        }

        public void Remove(string id) => _active.TryRemove(id, out _);
    }
}
