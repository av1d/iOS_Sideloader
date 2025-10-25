# iOS Sideloader

A Flask-based web application for managing sideloaded iOS applications remotely. Upload and install IPA files to your jailbroken iOS device and manage installed applications through a web interface. Allows you to add and remove applications quickly, without need of iTunes or other convoluted methods.

Tested on an iPod 4G running iOS 6.1.6 which was jailbroken with [Legacy iOS Kit](https://github.com/LukeZGD/Legacy-iOS-Kit/) on Ubuntu 22.04.

Some paths and methods may need to be updated for other devices or iOS versions. I have no knowledge how to do this.

## Features

- **Remote File Upload**: Transfer IPA files to your iOS device via SCP
- **Local File Upload**: Optionally lists local IPA files with a 1-click upload button
- **Application Management**: View and manage sideloaded applications
- **Application Removal**: Uninstall applications directly from the web interface
- **Real-time Status**: Monitor upload and operation progress
- **SpringBoard Auto-Restart**: Automatically refreshes the home screen after app removal

## Prerequisites

- Python 3.x
- A jailbroken iOS device with SSH access enabled
- Install 'IPA Installer Console' on your device from Cydia (Cydia is installed during jailbreak)
- Network connectivity between your computer and iOS device (same network or accessible IP)
- SSH credentials for your iOS device (default: user=root, password=alpine)

## Installation

1. Clone or download this repository:
```bash
git clone <repository-url>
cd <project-directory>
```

2. Install required Python packages:
```bash
pip install -r requirements.txt
```

The required dependencies are:
- flask
- werkzeug
- paramiko
- scp

3. Configure your iOS device settings in `settings.json`:
```json
{
  "REMOTE_IP": "192.168.0.27",
  "REMOTE_USER": "root",
  "REMOTE_PASS": "alpine",
  "REMOTE_PATH": "/var/mobile/Downloads"
}
```

Update these values to match your iOS device:
- `REMOTE_IP`: Your iOS device's IP address
- `REMOTE_USER`: SSH username (typically "root" for jailbroken devices)
- `REMOTE_PASS`: SSH password (default is "alpine" but should be changed for security)
- `REMOTE_PATH`: Destination path on iOS device for uploaded files

## Project Structure

```
project-directory/
├── app.py                  # Main Flask application
├── requirements.txt        # Python dependencies
├── settings.json          # Configuration file
├── license.txt            # MIT License
├── templates/             # HTML templates
│   ├── upload.html        # File upload interface
│   ├── manage.html        # App management interface
│   └── status.html        # Status display page
└── uploads/               # Temporary storage for uploaded files
```

## Usage

### Starting the Application

1. Run the Flask application:
```bash
python app.py
```

2. Access the web interface from your browser at:
```
http://localhost:5000
```

### Accessing from LAN

If you plan to access the app on a LAN from another machine, you may need to update this line in `app.py`:

```python
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
```

Change `host='0.0.0.0'` to your actual local IP address (e.g., `host='192.168.1.100'`), then access from other devices using:

```
http://<your-computer-ip>:5000
```

### Uploading Applications

1. Navigate to the home page (`http://<your-computer-ip>:5000`)
2. Configure your iOS device settings if needed (IP, credentials, path)
3. Select an IPA file using the file picker
4. Click upload
5. Monitor the upload progress on the status page

### Managing Applications

1. Navigate to `/manage` to view installed sideloaded applications
2. Applications are listed by name
3. Click the uninstall button next to any application to remove it
4. The SpringBoard will automatically restart to refresh the home screen of your iOS device

### Viewing Status

The `/status` page displays real-time information about:
- Connection status
- Upload progress with percentage and bytes transferred
- Operation completion or error messages

## Configuration

You can modify settings either by:
- Editing `settings.json` directly
- Using the web interface form on the upload page
- You can use appinstaller instead of IPA Installer, just change the command in app.py

### Security Considerations

- Change the default SSH password on your iOS device from "alpine" to something secure
- This application runs with `debug=True` by default - disable for production use
- Be cautious when exposing the application to your local network

## How It Works

1. **Upload Process**: Files are uploaded to the local `uploads/` folder, then transferred to the iOS device via SCP
2. **App Listing**: Scans `/User/Applications` on the iOS device for UUID folders and extracts app names
3. **App Removal**: Deletes the UUID folder and restarts SpringBoard using SSH commands
4. **Threading**: Upload and deletion operations run in background threads to prevent blocking

## Troubleshooting

**Cannot connect to iOS device:**
- Verify SSH is enabled on your jailbroken device
- Check that both devices are on the same network
- Confirm the IP address is correct
- Test SSH connection manually: `ssh root@<device-ip>`

**Upload fails:**
- Ensure the destination path exists on the iOS device
- Check available storage space
- Verify file permissions

**Apps not appearing in manage page:**
- Confirm apps are installed in `/User/Applications`
- Check SSH credentials are correct
- Some system apps won't appear (only sideloaded apps in User folder)
- Restart SpringBoard or the device

**Cannot access the web interface from another device:**
- Update the `host` parameter in `app.py` to your computer's local IP address instead of `0.0.0.0`
- Check firewall settings on the host computer
- Verify both devices are on the same network

## License

MIT License - See `license.txt` for full details.

Copyright (c) 2025 av1d

## Version

Current version: 1.0.4

## Contributing

Contributions are welcome. Please ensure any modifications maintain compatibility with jailbroken iOS devices and follow the existing code structure.

## Support

Sorry, I cannot offer support on this app but feel free to post issues.

## Disclaimer

This tool is intended for managing your own jailbroken iOS devices. Users are responsible for complying with all applicable laws and terms of service. Jailbreaking may void warranties and affect device security. I'm not responsible for any data loss, device bricking, etc. Use at your own risk.
