using System.Collections.ObjectModel;
using System.IO;
using System.Windows;
using System.Windows.Controls;
using Microsoft.Win32;
using WinForms = System.Windows.Forms;

namespace DeckShare;

public partial class MainWindow : Window
{
    private AppSettings _settings;
    private readonly ObservableCollection<ProgressRow> _progressRows = [];
    private CancellationTokenSource? _cancellation;
    private bool _loading = true;
    private string _totalEta = "--";

    public MainWindow()
    {
        InitializeComponent();
        _settings = SettingsStore.Load();
        SourcesGrid.ItemsSource = _settings.Sources;
        ProgressGrid.ItemsSource = _progressRows;
        ParallelBox.ItemsSource = Enumerable.Range(1, 8);
        LoadSettings();
        ApplyLanguage();
        _loading = false;
        Closing += (_, _) => SaveSettings();
    }

    private string T(string key, params object[] args) => Localization.Get(_settings.Language, key, args);

    private void LoadSettings()
    {
        HostBox.Text = _settings.Host;
        PortBox.Text = _settings.Port.ToString();
        UserBox.Text = _settings.Username;
        DefaultPathBox.Text = _settings.DefaultRemotePath;
        IdentityBox.Text = _settings.IdentityFile;
        SavePasswordCheck.IsChecked = _settings.SavePassword;
        ParallelBox.SelectedItem = Math.Clamp(_settings.ParallelTransfers, 1, 8);
        PasswordRadio.IsChecked = _settings.AuthMethod != "key";
        KeyRadio.IsChecked = _settings.AuthMethod == "key";
        LanguageBox.SelectedIndex = _settings.Language == "en" ? 1 : 0;
        if (_settings.SavePassword && _settings.AuthMethod == "password")
        {
            SecretBox.Password = CredentialManager.Read(CredentialManager.Target(_settings)) ?? "";
        }
        UpdateAuthControls();
    }

    private bool ReadSettings(bool validate)
    {
        if (!int.TryParse(PortBox.Text, out var port) || port is < 1 or > 65535 || string.IsNullOrWhiteSpace(HostBox.Text) || string.IsNullOrWhiteSpace(UserBox.Text))
        {
            if (validate) System.Windows.MessageBox.Show(T("invalidSettings"), "DeckShare", MessageBoxButton.OK, MessageBoxImage.Error);
            return false;
        }

        _settings.Host = HostBox.Text.Trim();
        _settings.Port = port;
        _settings.Username = UserBox.Text.Trim();
        _settings.DefaultRemotePath = NormalizeRemote(DefaultPathBox.Text);
        _settings.AuthMethod = KeyRadio.IsChecked == true ? "key" : "password";
        _settings.IdentityFile = IdentityBox.Text.Trim();
        _settings.SavePassword = SavePasswordCheck.IsChecked == true && _settings.AuthMethod == "password";
        _settings.ParallelTransfers = ParallelBox.SelectedItem is int parallel ? parallel : 1;

        if (validate && _settings.AuthMethod == "password" && string.IsNullOrEmpty(SecretBox.Password))
        {
            System.Windows.MessageBox.Show(T("passwordRequired"), "DeckShare", MessageBoxButton.OK, MessageBoxImage.Error);
            return false;
        }
        if (validate && _settings.AuthMethod == "key" && !File.Exists(_settings.IdentityFile))
        {
            System.Windows.MessageBox.Show(T("keyRequired"), "DeckShare", MessageBoxButton.OK, MessageBoxImage.Error);
            return false;
        }
        return true;
    }

    private void SaveSettings()
    {
        if (!ReadSettings(false)) return;
        var target = CredentialManager.Target(_settings);
        if (_settings.SavePassword && !string.IsNullOrEmpty(SecretBox.Password))
        {
            CredentialManager.Save(target, _settings.Username, SecretBox.Password);
        }
        else if (!_settings.SavePassword)
        {
            CredentialManager.Delete(target);
        }
        SettingsStore.Save(_settings);
    }

    private void ApplyLanguage()
    {
        Title = T("title");
        ConnectionGroup.Header = T("connection");
        HostLabel.Text = T("host");
        PortLabel.Text = T("port");
        UserLabel.Text = T("user");
        DefaultPathLabel.Text = T("defaultPath");
        AuthLabel.Text = T("auth");
        PasswordRadio.Content = T("password");
        KeyRadio.Content = T("key");
        SecretLabel.Text = KeyRadio.IsChecked == true ? T("key") : T("password");
        SavePasswordCheck.Content = T("savePassword");
        IdentityLabel.Text = T("identity");
        IdentityBrowseButton.Content = T("browse");
        ParallelLabel.Text = T("parallel");
        SourcesGroup.Header = T("sources");
        LocalPathColumn.Header = T("localFolder");
        RemotePathColumn.Header = T("remoteFolder");
        AddButton.Content = T("add");
        RemoveButton.Content = T("remove");
        TestButton.Content = T("test");
        TransferButton.Content = T("transfer");
        StopButton.Content = T("stop");
        ProgressGroup.Header = T("progress");
        FileColumn.Header = T("file");
        DestinationColumn.Header = T("destination");
        SpeedColumn.Header = T("speed");
        PercentColumn.Header = T("percent");
        EtaColumn.Header = T("fileEta");
        TotalEtaText.Text = T("totalEta", _totalEta);
        LogGroup.Header = T("log");
        if (!IsBusy()) StatusText.Text = T("ready");
    }

    private void UpdateAuthControls()
    {
        var key = KeyRadio.IsChecked == true;
        IdentityBox.IsEnabled = key;
        IdentityBrowseButton.IsEnabled = key;
        SavePasswordCheck.IsEnabled = !key;
        SecretLabel.Text = key ? T("key") : T("password");
    }

    private void LanguageBox_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (_loading || LanguageBox.SelectedItem is not ComboBoxItem item) return;
        _settings.Language = item.Tag?.ToString() == "en" ? "en" : "ru";
        ApplyLanguage();
        SaveSettings();
    }

    private void AuthRadio_Checked(object sender, RoutedEventArgs e)
    {
        if (!IsInitialized) return;
        UpdateAuthControls();
    }

    private void AddButton_Click(object sender, RoutedEventArgs e)
    {
        using var dialog = new WinForms.FolderBrowserDialog();
        if (dialog.ShowDialog() != WinForms.DialogResult.OK) return;
        if (_settings.Sources.Any(source => string.Equals(source.LocalPath, dialog.SelectedPath, StringComparison.OrdinalIgnoreCase))) return;
        _settings.Sources.Add(new TransferSource { LocalPath = dialog.SelectedPath, RemotePath = NormalizeRemote(DefaultPathBox.Text) });
        SaveSettings();
    }

    private void RemoveButton_Click(object sender, RoutedEventArgs e)
    {
        foreach (var source in SourcesGrid.SelectedItems.Cast<TransferSource>().ToList()) _settings.Sources.Remove(source);
        SaveSettings();
    }

    private void IdentityBrowseButton_Click(object sender, RoutedEventArgs e)
    {
        var dialog = new Microsoft.Win32.OpenFileDialog { CheckFileExists = true };
        if (dialog.ShowDialog() == true) IdentityBox.Text = dialog.FileName;
    }

    private async void TestButton_Click(object sender, RoutedEventArgs e)
    {
        if (!PrepareRun()) return;
        await RunAsync(service => service.TestConnectionAsync(_cancellation!.Token), T("testing"));
    }

    private async void TransferButton_Click(object sender, RoutedEventArgs e)
    {
        if (!PrepareRun()) return;
        if (_settings.Sources.Count == 0)
        {
            System.Windows.MessageBox.Show(T("noSources"), "DeckShare", MessageBoxButton.OK, MessageBoxImage.Error);
            return;
        }
        await RunAsync(service => service.TransferAsync(_cancellation!.Token), T("transferring"));
    }

    private bool PrepareRun()
    {
        if (IsBusy() || !ReadSettings(true)) return false;
        SaveSettings();
        _progressRows.Clear();
        _totalEta = "--";
        TotalEtaText.Text = T("totalEta", _totalEta);
        _cancellation = new CancellationTokenSource();
        return true;
    }

    private async Task RunAsync(Func<TransferService, Task> action, string status)
    {
        SetBusy(true, status);
        var service = new TransferService(_settings, SecretBox.Password, AppendLog, UpdateProgress, RemoveProgress);
        try
        {
            await action(service);
        }
        catch (OperationCanceledException)
        {
            AppendLog("error", T("stopped"));
        }
        catch (Exception ex)
        {
            AppendLog("error", T("error", ex.Message));
        }
        finally
        {
            _cancellation?.Dispose();
            _cancellation = null;
            SetBusy(false, T("ready"));
        }
    }

    private void StopButton_Click(object sender, RoutedEventArgs e)
    {
        StatusText.Text = T("stopping");
        _cancellation?.Cancel();
    }

    private void SetBusy(bool busy, string status)
    {
        TestButton.IsEnabled = !busy;
        TransferButton.IsEnabled = !busy;
        StopButton.IsEnabled = busy;
        StatusText.Text = status;
    }

    private bool IsBusy() => _cancellation is not null;

    private void AppendLog(string level, string text)
    {
        Dispatcher.Invoke(() =>
        {
            LogBox.AppendText($"[{DateTime.Now:HH:mm:ss}] {text}{Environment.NewLine}");
            LogBox.ScrollToEnd();
        });
    }

    private void UpdateProgress(ProgressUpdate update)
    {
        Dispatcher.Invoke(() =>
        {
            var row = _progressRows.FirstOrDefault(item => item.Id == update.Id);
            if (row is null)
            {
                row = new ProgressRow { Id = update.Id };
                _progressRows.Add(row);
            }
            row.FileName = update.FileName;
            row.Destination = update.Destination;
            row.Speed = update.Speed;
            row.Percent = update.Percent;
            row.Eta = update.FileEta;
            _totalEta = update.TotalEta;
            TotalEtaText.Text = T("totalEta", _totalEta);
        });
    }

    private void RemoveProgress(string id)
    {
        Dispatcher.Invoke(() =>
        {
            var row = _progressRows.FirstOrDefault(item => item.Id == id);
            if (row is not null) _progressRows.Remove(row);
            if (_progressRows.Count == 0)
            {
                _totalEta = "--";
                TotalEtaText.Text = T("totalEta", _totalEta);
            }
        });
    }

    private static string NormalizeRemote(string value) =>
        "/" + string.Join('/', value.Replace('\\', '/').Split('/', StringSplitOptions.RemoveEmptyEntries));
}
