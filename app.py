import os
import json
import threading
import re
from flask import Flask, render_template, request, redirect, url_for
from werkzeug.utils import secure_filename
from paramiko import SSHClient, AutoAddPolicy
from scp import SCPClient

# iOS Sideloader
# (c) 2025 av1d
VERSION = "1.0.8"

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

SETTINGS_FILE = 'settings.json'
STATUS = []

def load_settings():
    with open(SETTINGS_FILE, 'r') as f:
        settings = json.load(f)
        # Ensure LOCAL_IPA_PATHS exists
        if 'LOCAL_IPA_PATHS' not in settings:
            settings['LOCAL_IPA_PATHS'] = []
        return settings

def save_settings(data):
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def scan_local_ipas(paths):
    """
    Scans the provided paths for .ipa files.
    Returns: list of dicts {filename: , full_path: }
    """
    results = []
    for path in paths:
        if not os.path.exists(path):
            continue
        try:
            for item in os.listdir(path):
                if item.lower().endswith('.ipa'):
                    full_path = os.path.join(path, item)
                    results.append({
                        'filename': item,
                        'full_path': full_path
                    })
        except Exception as e:
            STATUS.append(f"Error scanning {path}: {str(e)}")
    return results

def cleanup_existing_app(bundle_id, client):
    """
    Cleans up an existing app installation by bundle ID,
    with aggressive receipts/caches deletion.
    Returns True if cleanup was successful, False otherwise.
    """
    STATUS.append(f'Cleaning up existing installation of {bundle_id}...')
    try:
        # Find all UUIDs that might contain this app
        find_uuid_cmd = f"grep -r '{bundle_id}' /User/Applications/*/Info.plist 2>/dev/null | cut -d'/' -f4"
        stdin, stdout, stderr = client.exec_command(find_uuid_cmd)
        uuids = [line.strip() for line in stdout.read().decode().strip().split('\n') if line.strip()]
        if not uuids:
            STATUS.append('No UUID found, trying uninstall by bundle ID only...')
            uuids = []
        uninstall_cmd = f"ipainstaller -u {bundle_id}"
        STATUS.append(f'Running: {uninstall_cmd}')
        stdin, stdout, stderr = client.exec_command(uninstall_cmd)
        out = stdout.read().decode()
        err = stderr.read().decode()
        if out:
            STATUS.append(f'STDOUT: {out}')
        if err:
            STATUS.append(f'STDERR: {err}')
        for uuid in uuids:
            STATUS.append(f'Cleaning up UUID: {uuid}')
            cleanup_cmds = [
                f"killall -9 $(basename $(ls /User/Applications/{uuid}/*.app 2>/dev/null) .app) 2>/dev/null || true",
                f"rm -rf /User/Applications/{uuid}",
                f"rm -rf /var/mobile/Containers/Data/Application/{uuid}",
                f"rm -rf /var/mobile/Containers/Bundle/Application/{uuid}",
                f"rm -rf /var/mobile/Library/Preferences/*{uuid}*.plist",
                f"rm -rf /var/mobile/Library/Caches/*{uuid}*",
                f"rm -rf /var/mobile/Library/Application\\ Support/*{uuid}*",
                f"rm -rf /var/mobile/Library/WebKit/*{uuid}*",
                f"rm -rf /var/mobile/Library/Cookies/*{uuid}*",
                f"rm -rf /var/mobile/Library/Saved\\ Application\\ State/*{uuid}*",
                f"rm -rf /var/mobile/Documents/*{uuid}*"
            ]
            for cmd in cleanup_cmds:
                STATUS.append(f'Running: {cmd}')
                stdin, stdout, stderr = client.exec_command(cmd)
                stdout.channel.recv_exit_status()
        # Bundle ID based cleanup (aggressive)
        bundle_cleanup_cmds = [
            f"rm -rf /var/mobile/Library/Preferences/*{bundle_id}*.plist",
            f"rm -rf /var/mobile/Library/Caches/*{bundle_id}*",
            f"rm -rf /var/mobile/Library/Application\\ Support/*{bundle_id}*",
            f"rm -rf /var/db/receipts/*{bundle_id}*",
            f"rm -rf /var/mobile/Library/Logs/CrashReporter/*{bundle_id}*",
            "rm -rf /var/mobile/Library/Caches/com.apple.mobile.installation.plist"
        ]
        for cmd in bundle_cleanup_cmds:
            STATUS.append(f'Running: {cmd}')
            stdin, stdout, stderr = client.exec_command(cmd)
            stdout.channel.recv_exit_status()
        STATUS.append('Refreshing SpringBoard cache...')
        stdin, stdout, stderr = client.exec_command("uicache -a")
        stdout.channel.recv_exit_status()
        STATUS.append('Aggressive cleanup complete.')
        return True
    except Exception as e:
        STATUS.append(f'Error during cleanup: {str(e)}')
        return False

def scp_and_remote(filename, settings):
    STATUS.clear()
    try:
        STATUS.append(f'Connecting to {settings["REMOTE_IP"]}...')
        client = SSHClient()
        client.set_missing_host_key_policy(AutoAddPolicy())
        client.connect(settings['REMOTE_IP'], username=settings['REMOTE_USER'], password=settings['REMOTE_PASS'])
        STATUS.append(f'Uploading {filename}...')
        def progress(fname, size, sent):
            percent = float(sent) / float(size) * 100
            STATUS.append(f'Uploading {fname}: {percent:.2f}% [{sent}/{size}]')
        with SCPClient(client.get_transport(), progress=progress) as scp:
            scp.put(filename, settings['REMOTE_PATH'])
        STATUS.append('Upload complete.')
        basename = os.path.basename(filename)
        remote_path_filename = f"'{settings['REMOTE_PATH']}/{basename}'"
        for cmd in [
            f'chmod 644 {remote_path_filename}',
            f'chown mobile:mobile {remote_path_filename}',
            f'ipainstaller {remote_path_filename}'
        ]:
            STATUS.append(f'Running remote command: {cmd}')
            stdin, stdout, stderr = client.exec_command(cmd)
            out = stdout.read().decode()
            err = stderr.read().decode()
            code = stdout.channel.recv_exit_status()
            STATUS.append(f'Exit code: {code}')
            if out:
                STATUS.append(f'STDOUT: {out}')
            if err:
                STATUS.append(f'STDERR: {err}')
        # Check ipainstaller output for stuck install
        out_lower = out.lower()
        if 'already installed' in out_lower:
            STATUS.append('App is already installed but with artifacts. Attempting aggressive cleanup and retry...')
            bundle_id_match = re.search(r'Analyzing.*?([a-zA-Z0-9\.\-]+).*?\.ipa', out)
            if not bundle_id_match:
                bundle_id_match = re.search(r'([a-zA-Z][a-zA-Z0-9]*(?:\.[a-zA-Z][a-zA-Z0-9]*)+)', basename)
            if bundle_id_match:
                potential_bundle_id = bundle_id_match.group(1)
                STATUS.append(f'Detected potential bundle ID: {potential_bundle_id}')
                cleanup_success = cleanup_existing_app(potential_bundle_id, client)
                if cleanup_success:
                    STATUS.append('Retrying installation...')
                    stdin, stdout, stderr = client.exec_command(f'ipainstaller {remote_path_filename}')
                    out = stdout.read().decode()
                    err = stderr.read().decode()
                    code = stdout.channel.recv_exit_status()
                    STATUS.append(f'Exit code: {code}')
                    if out:
                        STATUS.append(f'STDOUT: {out}')
                    if err:
                        STATUS.append(f'STDERR: {err}')
                    if code == 0 and 'already installed' not in out.lower():
                        STATUS.append('Installation successful after aggressive cleanup!')
                    else:
                        STATUS.append('Installation may have failed unless otherwise noted above. Manual intervention may be required.')
                else:
                    STATUS.append('Aggressive cleanup failed. Cannot retry installation.')
            else:
                STATUS.append('Could not detect bundle ID from output. Cannot auto-cleanup.')
        client.close()
        STATUS.append('All operations complete.')
    except Exception as e:
        STATUS.append(f'Error: {str(e)}')
    # Unlink/delete the IPA file from uploads folder after upload/install
    try:
        if filename.startswith("uploads" + os.sep) and os.path.exists(filename):
            os.remove(filename)
            STATUS.append(f"Deleted local file: {filename}")
    except Exception as e:
        STATUS.append(f"Error deleting local file: {str(e)}")

def list_apps(settings):
    """
    Scans /User/Applications only for UUID folders and their .app names.
    Returns: list of dicts {app_name: , uuid: }
    """
    try:
        client = SSHClient()
        client.set_missing_host_key_policy(AutoAddPolicy())
        client.connect(settings['REMOTE_IP'], username=settings['REMOTE_USER'], password=settings['REMOTE_PASS'])
        uuid_dirs_cmd = "ls -1 /User/Applications"
        stdin, stdout, stderr = client.exec_command(uuid_dirs_cmd)
        uuid_dirs = [line.strip() for line in stdout.read().decode().strip().split('\n') if '-' in line]
        results = []
        for uuid in uuid_dirs:
            app_cmd = f"ls -1d /User/Applications/{uuid}/*.app 2>/dev/null"
            stdin, stdout, stderr = client.exec_command(app_cmd)
            for app_line in stdout.read().decode().strip().split('\n'):
                if app_line and app_line.endswith('.app'):
                    app_name = app_line.rsplit('/', 1)[-1].replace('.app', '')
                    results.append({'app_name': app_name, 'uuid': uuid})
        client.close()
        return results
    except Exception as e:
        STATUS.append(f"Error listing apps: {str(e)}")
        return []

def nuke_app_folder(uuid, settings):
    """
    Fully removes IPA app: main, containers, caches, support files, preferences, running processes, SpringBoard refresh.
    """
    STATUS.clear()
    try:
        STATUS.append(f'Connecting for nuke: {uuid}')
        client = SSHClient()
        client.set_missing_host_key_policy(AutoAddPolicy())
        client.connect(settings['REMOTE_IP'], username=settings['REMOTE_USER'], password=settings['REMOTE_PASS'])
        cmds = [
            f"rm -rf /User/Applications/{uuid}",
            f"rm -rf /var/mobile/Containers/Data/Application/{uuid}",
            f"rm -rf /var/mobile/Containers/Bundle/Application/{uuid}",
            f"rm -rf /var/mobile/Library/Preferences/*{uuid}*.plist",
            f"rm -rf /var/mobile/Library/Caches/*{uuid}*",
            f"rm -rf /var/mobile/Library/Application\\ Support/*{uuid}*",
            f"killall $(basename $(ls /User/Applications/{uuid}/*.app 2>/dev/null | sed 's/\\.app$//')) || true",
            "uicache -a",
            "killall SpringBoard",
        ]
        for cmd in cmds:
            STATUS.append(f'Running: {cmd}')
            stdin, stdout, stderr = client.exec_command(cmd)
            out = stdout.read().decode()
            err = stderr.read().decode()
            code = stdout.channel.recv_exit_status()
            if out:
                STATUS.append(f'STDOUT: {out}')
            if err:
                STATUS.append(f'STDERR: {err}')
            STATUS.append(f'Exit code: {code}')
        client.close()
        # Optionally clean up upload folder (delete local IPA file if exists)
        local_ipa_path = os.path.join(app.config['UPLOAD_FOLDER'], f'{uuid}.ipa')
        if os.path.exists(local_ipa_path):
            os.remove(local_ipa_path)
            STATUS.append(f"Deleted local IPA: {local_ipa_path}")
        STATUS.append('App fully removed.')
    except Exception as e:
        STATUS.append(f"Error nuking app: {str(e)}")

@app.route('/', methods=['GET', 'POST'])
def upload_file():
    settings = load_settings()
    if request.method == 'POST':
        settings['REMOTE_IP'] = request.form['REMOTE_IP']
        settings['REMOTE_USER'] = request.form['REMOTE_USER']
        settings['REMOTE_PASS'] = request.form['REMOTE_PASS']
        settings['REMOTE_PATH'] = request.form['REMOTE_PATH']
        # Handle LOCAL_IPA_PATHS (comma-separated string -> list)
        paths_str = request.form.get('LOCAL_IPA_PATHS', '')
        settings['LOCAL_IPA_PATHS'] = [p.strip() for p in paths_str.split(',') if p.strip()]
        save_settings(settings)
        f = request.files['file']
        fname = secure_filename(f.filename)
        local_path = os.path.join(app.config['UPLOAD_FOLDER'], fname)
        f.save(local_path)
        thread = threading.Thread(target=scp_and_remote, args=(local_path, settings))
        thread.start()
        return redirect(url_for('status_page'))
    # Get local IPAs for display
    local_ipas = scan_local_ipas(settings.get('LOCAL_IPA_PATHS', []))
    return render_template('upload.html', settings=settings, local_ipas=local_ipas)

@app.route('/send_local', methods=['POST'])
def send_local_ipa():
    """Send a local IPA file to the device"""
    settings = load_settings()
    filepath = request.form.get('filepath')
    if not filepath or not os.path.exists(filepath):
        STATUS.append(f'Error: File not found: {filepath}')
        return redirect(url_for('status_page'))
    thread = threading.Thread(target=scp_and_remote, args=(filepath, settings))
    thread.start()
    return redirect(url_for('status_page'))

@app.route('/status')
def status_page():
    return render_template('status.html', status=STATUS)

@app.route('/manage')
def manage_apps():
    settings = load_settings()
    apps = list_apps(settings)
    return render_template('manage.html', apps=apps, settings=settings)

@app.route('/uninstall/', methods=['POST'])
def uninstall(uuid):
    settings = load_settings()
    thread = threading.Thread(target=nuke_app_folder, args=(uuid, settings))
    thread.start()
    return redirect(url_for('status_page'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
