# Building Antigravity Terminal as Windows Desktop App

## Quick Start (Run as Desktop App)

### 1. Install PyWebView
```bash
pip install pywebview
```

### 2. Run Desktop App
```bash
python desktop_app.py
```

This will open the terminal in a native Windows window instead of your browser.

---

## Building Standalone Executable (.exe)

### 1. Install Build Tools
```bash
pip install pyinstaller pywebview
```

### 2. Build the Executable
```bash
pyinstaller build.spec
```

### 3. Find Your App
The executable will be in: `dist/AntigravityTerminal.exe`

You can now:
- Run it without Python installed
- Share it with others
- Create a desktop shortcut
- Add to Windows startup

---

## File Size
- **Desktop App (Python required)**: ~5MB
- **Standalone .exe**: ~40-60MB (includes Python runtime)

---

## Features
✅ Native Windows window  
✅ No browser needed  
✅ System tray support (optional)  
✅ Auto-start with Windows (optional)  
✅ Offline capable (once built)

---

## Troubleshooting

### "Module not found" errors when building
```bash
pip install --upgrade pyinstaller
```

### App won't start
Check that PostgreSQL is running and `.env` is configured

### Want to add an icon?
1. Create or download a `.ico` file
2. Save as `icon.ico` in project root
3. In `build.spec`, change `icon=None` to `icon='icon.ico'`
4. Rebuild with `pyinstaller build.spec`
