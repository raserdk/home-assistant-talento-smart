# Uploading this project to GitHub

## Create the repository

1. Sign in to GitHub.
2. Create a new repository, for example:

   ```text
   home-assistant-talento-smart
   ```

3. Do not initialize it with a README if you plan to upload this folder as-is; this package already contains one.
4. Extract the GitHub ZIP locally.
5. Upload the **contents** of the extracted folder to the repository root.

The repository root should look like:

```text
.github/                 (optional if added later)
custom_components/
docs/
examples/
www/
.gitignore
.gitattributes
CHANGELOG.md
CONTRIBUTING.md
README.md
RELEASE_NOTES_1.0.0.md
```

## Important

GitHub's normal file uploader does not unpack a ZIP into repository files. Extract the ZIP first, then upload its contents, or use Git from the command line/Desktop app.

## Suggested repository description

```text
Unofficial Home Assistant integration for Grässlin Talento Smart Bluetooth timers — program read/write, time sync and AUTO/OVR/FIX control.
```

## Suggested topics

```text
home-assistant
homeassistant
bluetooth
ble
graesslin
talento-smart
time-switch
lovelace
```

## Release 1.0.0

After the repository is created, you can create a GitHub Release tagged:

```text
v1.0.0
```

Use `RELEASE_NOTES_1.0.0.md` as the release text.
