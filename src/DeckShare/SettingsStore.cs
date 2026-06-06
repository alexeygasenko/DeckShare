using System.IO;
using System.Text.Json;

namespace DeckShare;

public static class SettingsStore
{
    private static readonly JsonSerializerOptions JsonOptions = new() { WriteIndented = true };
    private static string DirectoryPath => Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "DeckShare");
    private static string FilePath => Path.Combine(DirectoryPath, "config.json");
    private static string LegacyFilePath => Path.Combine(AppContext.BaseDirectory, ".deckshare", "config.json");

    public static AppSettings Load()
    {
        try
        {
            var path = File.Exists(FilePath) ? FilePath : LegacyFilePath;
            if (!File.Exists(path)) return new AppSettings();
            return JsonSerializer.Deserialize<AppSettings>(File.ReadAllText(path), JsonOptions) ?? new AppSettings();
        }
        catch
        {
            return new AppSettings();
        }
    }

    public static void Save(AppSettings settings)
    {
        Directory.CreateDirectory(DirectoryPath);
        File.WriteAllText(FilePath, JsonSerializer.Serialize(settings, JsonOptions));
    }
}
