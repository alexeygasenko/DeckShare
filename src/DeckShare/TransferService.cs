using System.Collections.Concurrent;
using System.Diagnostics;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using Renci.SshNet;
using Renci.SshNet.Common;

namespace DeckShare;

public sealed class TransferService
{
    private const string VerifyHelper = """
        #!/bin/sh
        set -eu
        file="$1"
        progress="$2"
        : > "$progress"
        if dd if=/dev/null of=/dev/null status=progress 2>/dev/null; then
            dd if="$file" bs=1048576 status=progress 2>"$progress" | sha256sum | awk '{print $1}'
            exit 0
        fi

        chunk="$progress.chunk"
        fifo="$progress.fifo"
        result="$progress.result"
        hash_pid=""
        cleanup() {
            [ -n "$hash_pid" ] && kill "$hash_pid" 2>/dev/null || true
            rm -f "$chunk" "$fifo" "$result"
        }
        trap cleanup EXIT INT TERM
        rm -f "$chunk" "$fifo" "$result"
        mkfifo "$fifo"
        sha256sum < "$fifo" | awk '{print $1}' > "$result" &
        hash_pid=$!
        exec 3>"$fifo"
        block=0
        total=0
        while :; do
            dd if="$file" of="$chunk" bs=16777216 skip="$block" count=1 2>/dev/null
            bytes=$(wc -c < "$chunk")
            [ "$bytes" -eq 0 ] && break
            cat "$chunk" >&3
            total=$((total + bytes))
            printf '%s\n' "$total" > "$progress"
            block=$((block + 1))
        done
        exec 3>&-
        wait "$hash_pid"
        hash_pid=""
        cat "$result"
        """;

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
        _tracker.Start(tasks.Sum(task => task.Size * 2));
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
            if (source.IsMuted)
            {
                Log("info", "mutedFolder", source.LocalPath);
                continue;
            }
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
                ReportUpload(task, 0, started.Elapsed);
                string localHash;
                using (var hash = SHA256.Create())
                using (var input = File.OpenRead(task.LocalPath))
                using (var hashingInput = new CryptoStream(input, hash, CryptoStreamMode.Read))
                {
                    sftp.UploadFile(hashingInput, task.TempPath, true, sent =>
                    {
                        cancellationToken.ThrowIfCancellationRequested();
                        ReportUpload(task, checked((long)sent), started.Elapsed);
                    });
                    localHash = Convert.ToHexString(hash.Hash ?? throw new InvalidDataException("Could not calculate local SHA-256.")).ToLowerInvariant();
                }

                cancellationToken.ThrowIfCancellationRequested();
                Log("output", "verifying", task.TempPath);
                var remoteHash = VerifyRemoteHashWithProgress(sftp, ssh, task, cancellationToken);
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

    private void ReportUpload(UploadTask task, long sent, TimeSpan elapsed)
    {
        var seconds = Math.Max(elapsed.TotalSeconds, 0.001);
        var speed = sent / seconds;
        var total = _tracker.UpdateUpload(task.Id, sent, speed);
        var fileEta = speed > 0 ? (task.Size - sent) / speed : double.NaN;
        Report(task, T("phaseUploading"), sent, speed, fileEta, total);
    }

    private string VerifyRemoteHashWithProgress(SftpClient sftp, SshClient ssh, UploadTask task, CancellationToken cancellationToken)
    {
        var helperPath = $"/tmp/deckshare-verify-{task.Id}.sh";
        var progressPath = $"/tmp/deckshare-verify-{task.Id}.progress";
        try
        {
            using (var helper = new MemoryStream(new UTF8Encoding(false).GetBytes(VerifyHelper)))
            {
                sftp.UploadFile(helper, helperPath, true);
            }
            RunChecked(ssh, $"chmod 700 -- {Quote(helperPath)}");

            _tracker.BeginVerification(task.Id, task.Size);
            var started = Stopwatch.StartNew();
            using var command = ssh.CreateCommand($"{Quote(helperPath)} {Quote(task.TempPath)} {Quote(progressPath)}");
            var asyncResult = command.BeginExecute();
            try
            {
                while (!asyncResult.IsCompleted)
                {
                    if (cancellationToken.IsCancellationRequested)
                    {
                        command.CancelAsync(false, 2000);
                        cancellationToken.ThrowIfCancellationRequested();
                    }

                    var verified = ReadVerifiedBytes(sftp, progressPath, task.Size);
                    ReportVerification(task, verified, started.Elapsed);
                    Thread.Sleep(250);
                }

                command.EndExecute(asyncResult);
                if (command.ExitStatus != 0)
                {
                    throw new SshException(string.IsNullOrWhiteSpace(command.Error) ? "Remote verification helper failed." : command.Error.Trim());
                }
                ReportVerification(task, task.Size, started.Elapsed);
                return command.Result.Trim().Split(' ', StringSplitOptions.RemoveEmptyEntries)[0];
            }
            catch
            {
                if (!asyncResult.IsCompleted) command.CancelAsync(false, 2000);
                throw;
            }
        }
        finally
        {
            try { RemoveIfExists(sftp, helperPath); } catch { }
            try { RemoveIfExists(sftp, progressPath); } catch { }
            try { RemoveIfExists(sftp, progressPath + ".chunk"); } catch { }
            try { RemoveIfExists(sftp, progressPath + ".fifo"); } catch { }
            try { RemoveIfExists(sftp, progressPath + ".result"); } catch { }
        }
    }

    private void ReportVerification(UploadTask task, long verified, TimeSpan elapsed)
    {
        var seconds = Math.Max(elapsed.TotalSeconds, 0.001);
        var speed = verified / seconds;
        var total = _tracker.UpdateVerification(task.Id, task.Size, verified, speed);
        var fileEta = speed > 0 ? (task.Size - verified) / speed : double.NaN;
        Report(task, T("phaseVerifying"), verified, speed, fileEta, total);
    }

    private void Report(
        UploadTask task,
        string phase,
        long processed,
        double speed,
        double fileEta,
        (string Eta, string Speed) total)
    {
        _progress(new ProgressUpdate(
            task.Id,
            Path.GetFileName(task.LocalPath),
            RemoteDirectory(task.RemotePath),
            phase,
            FormatSpeed(speed),
            FormatPercent(processed, task.Size),
            FormatDuration(fileEta),
            total.Eta,
            total.Speed));
    }

    private static long ReadVerifiedBytes(SftpClient sftp, string progressPath, long fileSize)
    {
        try
        {
            if (!sftp.Exists(progressPath)) return 0;
            using var progress = new MemoryStream();
            sftp.DownloadFile(progressPath, progress);
            var text = Encoding.UTF8.GetString(progress.ToArray()).Replace('\r', '\n');
            var bytes = Regex.Matches(text, @"(?m)^(\d+)\s")
                .Select(match => long.TryParse(match.Groups[1].Value, out var value) ? value : 0)
                .DefaultIfEmpty(0)
                .Max();
            return Math.Min(bytes, fileSize);
        }
        catch
        {
            return 0;
        }
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
        private readonly ConcurrentDictionary<string, long> _activeWork = new();
        private readonly ConcurrentDictionary<string, double> _activeWorkSpeeds = new();
        private readonly ConcurrentDictionary<string, double> _activeNetworkSpeeds = new();
        private long _completed;
        private long _total;

        public void Start(long total)
        {
            _total = total;
            _completed = 0;
            _activeWork.Clear();
            _activeWorkSpeeds.Clear();
            _activeNetworkSpeeds.Clear();
        }

        public (string Eta, string Speed) UpdateUpload(string id, long bytes, double speed)
        {
            _activeWork[id] = bytes;
            _activeWorkSpeeds[id] = speed;
            _activeNetworkSpeeds[id] = speed;
            return Snapshot();
        }

        public void BeginVerification(string id, long size)
        {
            _activeWork[id] = size;
            _activeWorkSpeeds.TryRemove(id, out _);
            _activeNetworkSpeeds.TryRemove(id, out _);
        }

        public (string Eta, string Speed) UpdateVerification(string id, long size, long verified, double speed)
        {
            _activeWork[id] = size + verified;
            _activeWorkSpeeds[id] = speed;
            _activeNetworkSpeeds.TryRemove(id, out _);
            return Snapshot();
        }

        public (string Eta, string Speed) Snapshot()
        {
            lock (_sync)
            {
                var processed = _completed + _activeWork.Values.Sum();
                var workSpeed = _activeWorkSpeeds.Values.Sum();
                var networkSpeed = _activeNetworkSpeeds.Values.Sum();
                return (
                    FormatDuration(workSpeed > 0 ? Math.Max(_total - processed, 0) / workSpeed : double.NaN),
                    FormatSpeed(networkSpeed));
            }
        }

        public void Complete(string id, long size)
        {
            lock (_sync)
            {
                _activeWork.TryRemove(id, out _);
                _activeWorkSpeeds.TryRemove(id, out _);
                _activeNetworkSpeeds.TryRemove(id, out _);
                _completed += size * 2;
            }
        }

        public void Remove(string id)
        {
            _activeWork.TryRemove(id, out _);
            _activeWorkSpeeds.TryRemove(id, out _);
            _activeNetworkSpeeds.TryRemove(id, out _);
        }
    }
}
