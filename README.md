# DeckShare

DeckShare is a small Windows desktop utility for copying selected folders to a Steam Deck over SSH/SFTP.

## Requirements

- Python 3.10+.
- Python package dependencies from `requirements.txt`.
- SSH enabled on Steam Deck.

On Steam Deck, enable and start SSH:

```bash
sudo systemctl enable --now sshd
passwd
```

The default connection profile is:

- Host: `steamdeck.local`
- User: `deck`
- Port: `22`
- Remote folder: `/home/deck/DeckShare`

## Run

Double-click `run.bat`, or run:

```powershell
python -m pip install --target .deps -r requirements.txt
python deckshare.py
```

You can also double-click `install_requirements.bat` once, then use `run.bat`.

Add Windows directories, choose a Deck destination for each selected folder, check SSH, then press **Передать**. The default Deck path is used for newly added folders, but every folder can be pointed to its own Deck directory. DeckShare copies the contents of each selected Windows folder into its Deck destination; it does not create an extra remote folder with the Windows folder name. Settings are saved in `%APPDATA%\DeckShare\config.json`. If that location is not writable, DeckShare falls back to `.deckshare\config.json` next to the app.

## Notes

- The UI supports Russian and English. Use the language selector in the top-right corner.
- Login can use either the Steam Deck user password or a private SSH key.
- Passwords are not saved in the config file.
- Transfers use SFTP; if a remote file already exists, DeckShare skips it instead of overwriting it.
- During upload, the log shows the active file, per-file percentage, and current average speed.
- Extra files already present on the Steam Deck are not deleted.
- If `steamdeck.local` does not resolve, use the Steam Deck IP address shown in network settings.
