using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Runtime.CompilerServices;
using System.Text.Json.Serialization;

namespace DeckShare;

public sealed class TransferSource : INotifyPropertyChanged
{
    private string _localPath = "";
    private string _remotePath = "/home/deck/DeckShare";

    [JsonPropertyName("local_path")]
    public string LocalPath
    {
        get => _localPath;
        set => SetField(ref _localPath, value);
    }

    [JsonPropertyName("remote_path")]
    public string RemotePath
    {
        get => _remotePath;
        set => SetField(ref _remotePath, value);
    }

    public event PropertyChangedEventHandler? PropertyChanged;

    private void SetField(ref string field, string value, [CallerMemberName] string? propertyName = null)
    {
        if (field == value) return;
        field = value;
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(propertyName));
    }
}

public sealed class AppSettings
{
    [JsonPropertyName("host")]
    public string Host { get; set; } = "steamdeck.local";
    [JsonPropertyName("port")]
    public int Port { get; set; } = 22;
    [JsonPropertyName("username")]
    public string Username { get; set; } = "deck";
    [JsonPropertyName("remote_path")]
    public string DefaultRemotePath { get; set; } = "/home/deck/DeckShare";
    [JsonPropertyName("auth_method")]
    public string AuthMethod { get; set; } = "password";
    [JsonPropertyName("identity_file")]
    public string IdentityFile { get; set; } = "";
    [JsonPropertyName("save_password")]
    public bool SavePassword { get; set; }
    [JsonPropertyName("parallel_transfers")]
    public int ParallelTransfers { get; set; } = 1;
    [JsonPropertyName("language")]
    public string Language { get; set; } = "ru";
    [JsonPropertyName("sources")]
    public ObservableCollection<TransferSource> Sources { get; set; } = [];
}

public sealed class ProgressRow : INotifyPropertyChanged
{
    private string _fileName = "";
    private string _destination = "";
    private string _phase = "";
    private string _speed = "";
    private string _percent = "";
    private string _eta = "";
    private bool _isCompleted;

    public required string Id { get; init; }
    public string FileName { get => _fileName; set => SetField(ref _fileName, value); }
    public string Destination { get => _destination; set => SetField(ref _destination, value); }
    public string Phase { get => _phase; set => SetField(ref _phase, value); }
    public string Speed { get => _speed; set => SetField(ref _speed, value); }
    public string Percent { get => _percent; set => SetField(ref _percent, value); }
    public string Eta { get => _eta; set => SetField(ref _eta, value); }
    public bool IsCompleted { get => _isCompleted; set => SetField(ref _isCompleted, value); }

    public event PropertyChangedEventHandler? PropertyChanged;

    private void SetField(ref string field, string value, [CallerMemberName] string? propertyName = null)
    {
        if (field == value) return;
        field = value;
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(propertyName));
    }

    private void SetField(ref bool field, bool value, [CallerMemberName] string? propertyName = null)
    {
        if (field == value) return;
        field = value;
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(propertyName));
    }
}

public sealed record UploadTask(string Id, string LocalPath, string RemotePath, string TempPath, long Size);
public sealed record ProgressUpdate(
    string Id,
    string FileName,
    string Destination,
    string Phase,
    string Speed,
    string Percent,
    string FileEta,
    string TotalEta,
    string TotalSpeed);
