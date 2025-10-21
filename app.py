import os
import json
import threading
from flask import Flask, render_template, request, redirect, url_for
from werkzeug.utils import secure_filename
from paramiko import SSHClient, AutoAddPolicy
from scp import SCPClient

# iOS Sideloader
# (c) 2025 av1d
VERSION = "1.0.4"

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

SETTINGS_FILE = 'settings.json'
STATUS = []

def load_settings():
    with open(SETTINGS_FILE, 'r') as f:
        return json.load(f)

def save_settings(data):
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def scp_and_remote(filename, settings):
    STATUS.clear()
    try:
        STATUS.append(f'Connecting to {settings["REMOTE_IP"]}...')
        client = SSHClient()
        client.set_missing_host_key_policy(AutoAddPolicy())
        client.connect(settings['REMOTE_IP'],
                       username=settings['REMOTE_USER'],
                       password=settings['REMOTE_PASS'])
        STATUS.append(f'Uploading {filename}...')
        def progress(fname, size, sent):
            percent = float(sent) / float(size * 1.0) * 100
            STATUS.append(f'Uploading {fname}: {percent:.2f}% [{sent}/{size}]')
        with SCPClient(client.get_transport(), progress=progress) as scp:
            scp.put(filename, settings['REMOTE_PATH'])
        STATUS.append('Upload complete.')
        client.close()
    except Exception as e:
        STATUS.append(f'Error: {str(e)}')

def list_apps(settings):
    """
    Scans /User/Applications only for UUID folders and their .app names.
    Returns: list of dicts {app_name: <name>, uuid: <uuid>}
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
    """Deletes the UUID folder from /User/Applications, then restarts SpringBoard."""
    STATUS.clear()
    try:
        STATUS.append(f'Connecting for nuke: {uuid}')
        client = SSHClient()
        client.set_missing_host_key_policy(AutoAddPolicy())
        client.connect(settings['REMOTE_IP'], username=settings['REMOTE_USER'], password=settings['REMOTE_PASS'])
        cmd = f"rm -rf /User/Applications/{uuid}"
        STATUS.append(f'Running: {cmd}')
        stdin, stdout, stderr = client.exec_command(cmd)
        code = stdout.channel.recv_exit_status()

        # Restart SpringBoard for icon cleanup
        cmd2 = "killall SpringBoard"
        STATUS.append(f'Running: {cmd2}')
        stdin, stdout, stderr = client.exec_command(cmd2)
        code2 = stdout.channel.recv_exit_status()
        STATUS.append(f'Exit code: {code}; killall code: {code2}')
        client.close()
        STATUS.append('Done.')
    except Exception as e:
        STATUS.append(f"Error nuking folder: {str(e)}")

@app.route('/', methods=['GET', 'POST'])
def upload_file():
    settings = load_settings()
    if request.method == 'POST':
        settings['REMOTE_IP'] = request.form['REMOTE_IP']
        settings['REMOTE_USER'] = request.form['REMOTE_USER']
        settings['REMOTE_PASS'] = request.form['REMOTE_PASS']
        settings['REMOTE_PATH'] = request.form['REMOTE_PATH']
        save_settings(settings)
        f = request.files['file']
        fname = secure_filename(f.filename)
        local_path = os.path.join(app.config['UPLOAD_FOLDER'], fname)
        f.save(local_path)
        thread = threading.Thread(target=scp_and_remote, args=(local_path, settings))
        thread.start()
        return redirect(url_for('status_page'))
    return render_template('upload.html', settings=settings)

@app.route('/status')
def status_page():
    return render_template('status.html', status=STATUS)

@app.route('/manage')
def manage_apps():
    settings = load_settings()
    apps = list_apps(settings)
    return render_template('manage.html', apps=apps, settings=settings)

@app.route('/uninstall/<uuid>', methods=['POST'])
def uninstall(uuid):
    settings = load_settings()
    thread = threading.Thread(target=nuke_app_folder, args=(uuid, settings))
    thread.start()
    return redirect(url_for('status_page'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
