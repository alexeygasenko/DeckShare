# DeckShare

DeckShare is a portable Windows desktop application for copying selected folders to a Steam Deck over SSH/SFTP.

## Download and run

Download `DeckShare.exe` from the [latest GitHub release](https://github.com/alexeygasenko/DeckShare/releases/latest) and run it. The executable is self-contained: Python and .NET do not need to be installed.

On Steam Deck, enable SSH once:

```bash
sudo systemctl enable --now sshd
passwd
```

The default connection profile is:

- Host: `steamdeck.local`
- User: `deck`
- Port: `22`
- Remote folder: `/home/deck/DeckShare`

Add Windows folders, choose a separate Deck destination for each folder, check SSH, then press **Transfer**. DeckShare copies each selected folder's contents directly into its destination without creating an extra folder with the Windows folder name.

## Features

- Native Windows UI written in C# and WPF.
- Russian and English localization.
- Password or private SSH key authentication.
- Optional secure password storage in Windows Credential Manager.
- Configurable parallel file transfers.
- Resizable progress table showing every active file, destination, speed, percentage, and time left.
- Total ETA and aggregate network speed across all active transfers.
- Existing final files are skipped when their size matches.
- New or changed files upload as `.deckshare-part`, are verified with SHA-256, then replace the final file.
- Temporary files are removed after transfer errors or cancellation when the Deck remains reachable.
- Each Windows source folder can use its own destination on the Steam Deck.

Settings are saved in `%APPDATA%\DeckShare\config.json`. Passwords are never stored in that file.

## Build portable EXE

Requirements:

- Windows
- .NET 8 SDK

Run:

```powershell
.\build-portable.ps1
```

The self-contained single-file executable is written to `dist\DeckShare.exe`.
