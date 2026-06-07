import os
import re
import time
import threading
import subprocess
import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

# Global state for background maintenance tasks
maintenance_running = False
maintenance_output = []
maintenance_action = ""

def read_last_lines(filepath, n):
    """Efficiently read the last N lines of a file."""
    try:
        if not os.path.exists(filepath):
            return []
        with open(filepath, 'rb') as f:
            f.seek(0, 2)
            file_len = f.tell()
            buffer_size = 8192
            lines = []
            pos = file_len
            
            while pos > 0 and len(lines) <= n:
                pos = max(0, pos - buffer_size)
                f.seek(pos)
                chunk = f.read(file_len - pos if pos + buffer_size > file_len else buffer_size)
                lines = chunk.decode('utf-8', errors='ignore').splitlines()
                
            return lines[-n:]
    except Exception as e:
        print("Error reading last lines:", e)
        try:
            with open(filepath, 'r') as f:
                return f.readlines()[-n:]
        except Exception:
            return []

def get_acng_stats():
    """Scrape and parse the statistics from acng-report.html."""
    try:
        # Query with doCount to make sure statistics are recalculated
        url = "http://localhost:3142/acng-report.html?doCount=Count+Data"
        r = requests.get(url, timeout=5)
        if r.status_code != 200:
            return None
        
        soup = BeautifulSoup(r.text, 'html.parser')
        
        stats = {
            "fetched_startup": "0 B",
            "fetched_recent": "0 B",
            "served_startup": "0 B",
            "served_recent": "0 B",
            "hits_count": 0,
            "misses_count": 0,
            "total_requests": 0,
            "hit_rate_pct": 0.0,
            "hits_data": "0.00 MiB (0.00%)",
            "misses_data": "0.00 MiB (0.00%)",
            "total_data": "0.00 MiB",
            "data_hit_rate_pct": 0.0,
        }
        
        # 1. Parse high-level transfer statistics
        for row in soup.find_all('tr'):
            cells = row.find_all('td')
            if len(cells) >= 3:
                label = cells[0].get_text(strip=True)
                if "Data fetched:" in label:
                    stats["fetched_startup"] = cells[1].get_text(strip=True).replace(chr(160), ' ')
                    stats["fetched_recent"] = cells[2].get_text(strip=True).replace(chr(160), ' ')
                elif "Data served:" in label:
                    stats["served_startup"] = cells[1].get_text(strip=True).replace(chr(160), ' ')
                    stats["served_recent"] = cells[2].get_text(strip=True).replace(chr(160), ' ')
        
        # 2. Parse cache efficiency table (find row with date range)
        for row in soup.find_all('tr'):
            cells = [c.get_text(strip=True) for c in row.find_all('td')]
            if len(cells) == 9 and " - " in cells[0]:
                # Requests parsing
                hits_req_match = re.search(r'(\d+)\s*\(([\d\.]+)%\)', cells[2])
                misses_req_match = re.search(r'(\d+)\s*\(([\d\.]+)%\)', cells[3])
                total_req = cells[4]
                
                # Data parsing
                hits_data_match = re.search(r'([\d\.]+)\s*(\w+)\s*\(([\d\.]+)%\)', cells[6])
                
                if hits_req_match:
                    stats["hits_count"] = int(hits_req_match.group(1))
                    stats["hit_rate_pct"] = float(hits_req_match.group(2))
                if misses_req_match:
                    stats["misses_count"] = int(misses_req_match.group(1))
                if total_req.isdigit():
                    stats["total_requests"] = int(total_req)
                    
                stats["hits_data"] = cells[6].replace(chr(160), ' ')
                stats["misses_data"] = cells[7].replace(chr(160), ' ')
                stats["total_data"] = cells[8].replace(chr(160), ' ')
                
                if hits_data_match:
                    stats["data_hit_rate_pct"] = float(hits_data_match.group(3))
                    
        return stats
    except Exception as e:
        print("Error parsing acng stats:", e)
        return None

def parse_logs(limit=50):
    """Parse the raw logs into structured data and aggregate details."""
    log_path = "/var/log/apt-cacher-ng/apt-cacher.log"
    raw_lines = read_last_lines(log_path, 200) # Read last 200 for aggregations
    
    logs = []
    clients = {}
    repos = {}
    
    for line in reversed(raw_lines):
        line = line.strip()
        if not line:
            continue
        parts = line.split('|')
        if len(parts) >= 5:
            try:
                ts = int(parts[0])
                event_type = parts[1]
                size = int(parts[2])
                client_ip = parts[3]
                path = parts[4]
                
                # Format time
                local_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts))
                
                # Format size
                if size < 1024:
                    size_str = f"{size} B"
                elif size < 1024 * 1024:
                    size_str = f"{size/1024:.2f} KB"
                else:
                    size_str = f"{size/(1024*1024):.2f} MB"
                
                event_desc = "Client Request" if event_type == "I" else "Upstream Sync" if event_type == "O" else f"Info ({event_type})"
                
                # Aggregations
                clients[client_ip] = clients.get(client_ip, 0) + size
                
                # Extract repo name (first path element)
                repo_match = re.match(r'^([^/]+)', path)
                if repo_match:
                    repo_name = repo_match.group(1)
                    repos[repo_name] = repos.get(repo_name, 0) + 1
                
                if len(logs) < limit:
                    logs.append({
                        "timestamp": local_time,
                        "type": event_type,
                        "type_desc": event_desc,
                        "size": size_str,
                        "client_ip": client_ip,
                        "path": path
                    })
            except Exception as e:
                print("Error parsing log line:", e)
                
    # Sort aggregations
    top_clients = [{"ip": ip, "bytes": bytes_val, "formatted": f"{bytes_val/(1024*1024):.2f} MB" if bytes_val >= 1024*1024 else f"{bytes_val/1024:.2f} KB"} 
                   for ip, bytes_val in sorted(clients.items(), key=lambda x: x[1], reverse=True)[:5]]
    top_repos = [{"repo": repo, "count": count} for repo, count in sorted(repos.items(), key=lambda x: x[1], reverse=True)[:5]]
    
    return logs, top_clients, top_repos

def run_background_task(url, action_name):
    """Execute maintenance task and update global state."""
    global maintenance_running, maintenance_output, maintenance_action
    maintenance_running = True
    maintenance_action = action_name
    maintenance_output = [f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Starting administrative task: {action_name}..."]
    
    try:
        r = requests.get(url, stream=True, timeout=600)
        for line in r.iter_lines():
            if line:
                decoded_line = line.decode('utf-8', errors='ignore')
                # Strip HTML tags
                clean_line = re.sub(r'<[^>]+>', '', decoded_line).strip()
                if clean_line:
                    # Ignore inline scripts and styles
                    if "function " in clean_line or "var " in clean_line or "} else {" in clean_line or "checkOrUncheck" in clean_line:
                        continue
                    maintenance_output.append(clean_line)
        maintenance_output.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Task completed successfully.")
    except Exception as e:
        maintenance_output.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Error during task: {str(e)}")
    finally:
        maintenance_running = False

@app.route('/')
def index():
    # Render main dashboard template
    return render_template('index.html')

@app.route('/api/stats')
def api_stats():
    # Get stats from ACNG and logs
    stats = get_acng_stats()
    logs, top_clients, top_repos = parse_logs()
    
    # Check if port 3142 is up
    service_status = "online"
    try:
        r = requests.get("http://localhost:3142/", timeout=2)
    except Exception:
        service_status = "offline"
        
    return jsonify({
        "status": service_status,
        "cacher_stats": stats,
        "recent_logs": logs,
        "top_clients": top_clients,
        "top_repos": top_repos,
        "maintenance_running": maintenance_running,
        "maintenance_action": maintenance_action
    })

@app.route('/api/action', methods=['POST'])
def api_action():
    global maintenance_running
    if maintenance_running:
        return jsonify({"success": False, "error": "Another maintenance task is currently running."}), 400
        
    data = request.json or {}
    action = data.get("action")
    
    if not action:
        return jsonify({"success": False, "error": "No action specified."}), 400
        
    # Map actions to Apt-Cacher NG URLs
    base_url = "http://localhost:3142/acng-report.html"
    if action == "count":
        # Synchronous count (quick)
        get_acng_stats()
        return jsonify({"success": True, "message": "Statistics re-counted successfully."})
        
    elif action == "expire":
        url = f"{base_url}?doExpire=Start+Scan+and%2For+Expiration&abortOnErrors=aOe&purgeNow=pN"
        thread = threading.Thread(target=run_background_task, args=(url, "Cache Expiration & Cleanup"))
        thread.start()
        return jsonify({"success": True, "message": "Cache Expiration started in the background."})
        
    elif action == "show_unreferenced":
        url = f"{base_url}?justShow=Show+unreferenced"
        thread = threading.Thread(target=run_background_task, args=(url, "Scan Unreferenced Packages"))
        thread.start()
        return jsonify({"success": True, "message": "Scan for unreferenced packages started."})
        
    elif action == "remove_unreferenced":
        url = f"{base_url}?justRemove=Delete+unreferenced"
        thread = threading.Thread(target=run_background_task, args=(url, "Delete Unreferenced Packages"))
        thread.start()
        return jsonify({"success": True, "message": "Deletion of unreferenced packages started."})

    elif action == "show_damaged":
        url = f"{base_url}?justShowDamaged=Show+damaged"
        thread = threading.Thread(target=run_background_task, args=(url, "Scan Damaged Packages"))
        thread.start()
        return jsonify({"success": True, "message": "Scan for damaged packages started."})

    elif action == "remove_damaged":
        url = f"{base_url}?justRemoveDamaged=Delete+damaged"
        thread = threading.Thread(target=run_background_task, args=(url, "Delete Damaged Packages"))
        thread.start()
        return jsonify({"success": True, "message": "Deletion of damaged packages started."})
        
    return jsonify({"success": False, "error": f"Unknown action: {action}"}), 400

@app.route('/api/maintenance-status')
def maintenance_status():
    return jsonify({
        "running": maintenance_running,
        "action": maintenance_action,
        "output": maintenance_output
    })

@app.route('/api/restart-service', methods=['POST'])
def restart_service():
    try:
        subprocess.run(["systemctl", "restart", "apt-cacher-ng"], check=True)
        return jsonify({"success": True, "message": "Apt-Cacher NG service restarted successfully."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == '__main__':
    # Listen on all interfaces on port 8080
    app.run(host='0.0.0.0', port=8080, debug=False)
