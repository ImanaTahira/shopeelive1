#!/usr/bin/env python
import sys
import requests
import re
import threading
import time
import subprocess
import psutil
import os
import json
import shutil
import datetime
try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False

# Konstanta untuk subprocess creationflags (hanya untuk Windows)
SUBPROCESS_CREATE_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0

# Path ke FFmpeg yang sudah ada di project
FFMPEG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ffmpeg.exe")
if not os.path.exists(FFMPEG_PATH):
    FFMPEG_PATH = "ffmpeg"  # Gunakan FFmpeg dari PATH jika tidak ditemukan

# Variabel global
streaming_process = None
streaming_status = False
download_process = None
download_status = False
auto_reconnect = True
reconnect_attempts = 0
max_reconnect_attempts = 5  # Batas percobaan koneksi ulang
log_file = "shopee_live.log"  # File untuk menyimpan log

# Daftar user yang diizinkan
ALLOWED_USERS = {
    "admin": "passwordku123",
    "tim1": "rahasia456"
}

def clear_temp_files():
    """Membersihkan file sementara yang dibuat oleh script"""
    try:
        # Hapus file PowerShell sementara jika ada
        temp_ps_file = os.path.join(os.environ.get('TEMP', ''), 'run_shopee.ps1')
        temp_py_file = os.path.join(os.environ.get('TEMP', ''), 'shopee_live_temp.py')
        
        for file_path in [temp_ps_file, temp_py_file]:
            if os.path.exists(file_path):
                os.remove(file_path)
                print_log(f"File sementara dihapus: {file_path}")
        
        # Hapus file VBS jika ada
        temp_vbs_file = os.path.join(os.environ.get('TEMP', ''), 'invisible.vbs')
        if os.path.exists(temp_vbs_file):
            os.remove(temp_vbs_file)
            print_log(f"File sementara dihapus: {temp_vbs_file}")
    except Exception as e:
        print_log(f"Error saat membersihkan file sementara: {str(e)}")

def clear_logs(force=False):
    """Membersihkan file log"""
    try:
        if os.path.exists(log_file):
            # Buat backup log lama dengan timestamp
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            backup_file = f"{log_file}.{timestamp}.bak"
            
            # Coba pindahkan file log lama ke backup
            try:
                shutil.copy2(log_file, backup_file)
                print(f"[{time.strftime('%H:%M:%S')}] Log lama dicadangkan ke: {backup_file}")
            except Exception as backup_err:
                print(f"[{time.strftime('%H:%M:%S')}] Gagal membuat backup log: {str(backup_err)}")
            
            # Hapus isi file log
            with open(log_file, 'w') as f:
                f.write(f"=== Log dibersihkan pada {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
            
            if force:
                print(f"[{time.strftime('%H:%M:%S')}] File log dibersihkan oleh pengguna")
            else:
                print(f"[{time.strftime('%H:%M:%S')}] File log dibersihkan otomatis (melebihi 500 baris)")
    except Exception as e:
        print(f"[{time.strftime('%H:%M:%S')}] Error saat membersihkan log: {str(e)}")

def print_log(message):
    """Tampilkan pesan log dengan timestamp dan simpan ke file"""
    # Hanya tampilkan pesan penting
    important_messages = [
        "ERROR", "Error", "error",
        "Download selesai", "Streaming dimulai",
        "Streaming berhasil", "Streaming dihentikan"
    ]
    
    if any(msg in message for msg in important_messages):
        timestamp = time.strftime("[%H:%M:%S] ")
        log_message = f"{timestamp}{message}"
        print(log_message)
        
        # Tulis ke file log
        try:
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(log_message + "\n")
        except Exception as e:
            print(f"[ERROR] Gagal menulis ke file log: {str(e)}")

def check_session(cookie_string):
    """Memeriksa sesi dari cookie Shopee"""
    print_log("Mendapatkan data sesi...")
    url = 'https://creator.shopee.co.id/supply/api/lm/sellercenter/realtime/sessionList?page=1&pageSize=1&name='
    headers = {
        'Host': 'creator.shopee.co.id',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:122.0) Gecko/20100101 Firefox/122.0',
        'Accept': 'application/json',
        'Accept-Language': 'id,en-US;q=0.7,en;q=0.3',
        'Accept-Encoding': 'gzip, deflate, br',
        'Referer': 'https://creator.shopee.co.id/insight/live/list',
        'Content-Type': 'application/json',
        'X-Traceid': 'heG_qY0WxPfYS1WX7klFR',
        'Language': 'en',
        'X-Region': 'id',
        'X-Region-Domain': 'co.id',
        'X-Region-Timezone': '+0700',
        'X-Env': 'live',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'Te': 'trailers',
        'Cookie': cookie_string
    }
    
    try:
        response = requests.get(url, headers=headers)
        return response.json()
    except Exception as e:
        print_log(f"Error: {str(e)}")
        return None

def get_data_live(session_id, cookie_string):
    """Mendapatkan data live dari Shopee API"""
    print_log(f"Mendapatkan data live untuk session ID: {session_id}")
    url = f'https://live.shopee.co.id/api/v1/session/{session_id}/push_url_list?ver=2'
    headers = {
        'Host': 'live.shopee.co.id',
        'ls_net_unicodeid': '321454518',
        'x-shopee-client-timezone': 'Asia/Jakarta',
        'client-request-id': '799ed8f0-f88d-44f7-8b8f-d8cd39264047.207',
        'client-info': 'device_model=IN9023;os=0;os_version=30;client_version=31620;network=1;platform=1;language=id;cpu_model=Qualcomm+Technologies%2C+Inc+SDM636',
        'x-livestreaming-source': 'shopee',
        'x-ls-sz-token': 'Om9w2YHSSVM4mwzhy04Vuw==|ui3/GfDKzV9n2h+0KBIK2fSer8L5j2heZXdatTOd63pU0npKs5LEw2GhQOCsGa8a1ij8nONL8IJTsO9ustxRunkMwMbubcU=|44qNR/drvF5S6NKx|08|1',
        'x-livestreaming-auth': 'ls_android_v1_10001_1705749720_36f1e51f-333e-4c10-af48-e017d9d57d0c|mH2Ct50CD3f7jkmofKS3qwzDRKJz5mLr2T3/vfAgQRQ=',
        'time-type': '1705749720_2',
        'user-agent': 'okhttp/3.12.4 app_type=1',
        'content-type': 'application/json;charset=UTF-8',
        'Cookie': cookie_string
    }
    
    try:
        response = requests.get(url, headers=headers)
        data = response.json()
        push_urls = [addr['push_url'] for addr in data['data']['push_addr_list']]
        return push_urls
    except Exception as e:
        print_log(f"Error: {str(e)}")
        return []

def get_streaming_url(session_id, cookie_string):
    """Mengambil URL streaming dari API Shopee berdasarkan session ID dan cookie"""
    print_log(f"Mengambil URL streaming untuk session ID: {session_id}")
    headers = {
        'accept': 'application/json',
        'accept-language': 'en-US,en;q=0.9',
        'content-type': 'application/json',
        'language': 'en',
        'priority': 'u=1, i',
        'referer': f'https://creator.shopee.co.id/dashboard/live/{session_id}',
        'sec-ch-ua': '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36',
        'x-env': 'live',
        'x-region': 'id',
        'x-region-domain': 'co.id',
        'x-region-timezone': '+0700'
    }

    params = {
        'sessionId': session_id,
    }

    # Parse cookies string ke dictionary
    cookies = {}
    if cookie_string:
        cookie_pairs = cookie_string.split(';')
        for pair in cookie_pairs:
            if '=' in pair:
                key, value = pair.strip().split('=', 1)
                cookies[key] = value

    try:
        response = requests.get(
            'https://creator.shopee.co.id/supply/api/lm/sellercenter/realtime/dashboard/sessionInfo',
            params=params,
            cookies=cookies,
            headers=headers,
        )
        
        response_data = response.json()
        
        if 'data' in response_data and 'sessionStreamingUrl' in response_data['data']:
            return response_data['data']['sessionStreamingUrl'], response_data
        else:
            return None, response_data
    except Exception as e:
        return None, str(e)

def download_flv(flv_url, duration_minutes=20):
    """Download FLV dari URL selama durasi tertentu"""
    global download_process, download_status
    download_status = True
    
    # Buat direktori untuk menyimpan file
    download_dir = "downloaded_videos"
    if not os.path.exists(download_dir):
        os.makedirs(download_dir)
    
    # Nama file output dengan durasi
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    output_file = os.path.join(download_dir, f"shopee_live_{timestamp}_dur{duration_minutes}min.flv")
    
    print_log(f"Mulai mengunduh dari {flv_url}")
    print_log(f"File akan disimpan di: {output_file}")
    print_log(f"Durasi download diatur: {duration_minutes} menit")
    
    # Perintah FFmpeg untuk download tanpa parameter -t
    ffmpeg_download_cmd = [
        FFMPEG_PATH,
        "-i", flv_url,
        "-c", "copy",
        "-reconnect", "1",
        "-reconnect_streamed", "1", 
        "-reconnect_delay_max", "5",
        output_file
    ]
    
    try:
        cmd_str = " ".join(ffmpeg_download_cmd)
        print_log(f"Menjalankan: {cmd_str}")
        download_process = subprocess.Popen(
            ffmpeg_download_cmd, 
            stderr=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stdin=subprocess.PIPE,
            text=True,
            creationflags=SUBPROCESS_CREATE_NO_WINDOW
        )
        print_log(f"Proses download dimulai dengan PID: {download_process.pid}")
        
        # Inisialisasi progress bar
        if TQDM_AVAILABLE:
            pbar = tqdm(total=100, desc="Download Progress", unit="%")
        else:
            print("Download Progress: 0%", end="", flush=True)
        
        start_time = time.time()
        end_time = start_time + (duration_minutes * 60)
        last_progress = 0
        
        # Progress bar berbasis waktu berjalan
        while time.time() < end_time and download_process.poll() is None:
            elapsed = time.time() - start_time
            progress = min(100, int((elapsed / (duration_minutes * 60)) * 100))
            if progress > last_progress:
                last_progress = progress
                if TQDM_AVAILABLE:
                    pbar.n = progress
                    pbar.refresh()
                else:
                    print(f"\rDownload Progress: {progress}%", end="", flush=True)
            time.sleep(0.2)
        
        # Setelah waktu habis, hentikan proses FFmpeg secara tegas
        if download_process.poll() is None:
            print_log(f"Durasi download {duration_minutes} menit tercapai.")
            try:
                download_process.stdin.write('q\n')
                download_process.stdin.flush()
                time.sleep(2)
            except:
                pass
            if download_process.poll() is None:
                try:
                    download_process.terminate()
                    time.sleep(2)
                except:
                    pass
            if download_process.poll() is None:
                try:
                    download_process.kill()
                except:
                    pass
            # Tutup semua stream agar tidak deadlock
            try:
                download_process.stdout.close()
                download_process.stderr.close()
            except:
                pass
        
        # Tutup progress bar secara paksa
        if TQDM_AVAILABLE:
            pbar.n = 100
            pbar.refresh()
            pbar.close()
        else:
            print("\rDownload Progress: 100%")
        
        # Jangan tunggu output lagi, langsung cek file
        if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
            file_size_mb = os.path.getsize(output_file) / (1024*1024)
            print_log(f"Download selesai! File berhasil diunduh: {output_file}")
            print_log(f"Ukuran file: {file_size_mb:.2f} MB")
            download_status = True
            return output_file
        else:
            print_log(f"Download gagal. File tidak ada atau kosong.")
            download_status = False
            return None
    except Exception as e:
        print_log(f"Error download: {str(e)}")
        import traceback
        print_log(traceback.format_exc())
        download_status = False
        return None

# Fungsi stop_download yang lebih aman
def stop_download():
    """Menghentikan proses download dengan cara yang lebih aman"""
    global download_process, download_status
    
    try:
        if download_process is not None:
            print_log("Menghentikan proses download...")
            
            # Coba metode yang lebih lembut dulu
            if download_process.poll() is None:
                try:
                    # Kirim sinyal q untuk keluar dengan benar
                    download_process.stdin.write('q\n')
                    download_process.stdin.flush()
                    time.sleep(2)
                except:
                    pass
                
                # Jika masih berjalan, coba terminate
                if download_process.poll() is None:
                    try:
                        download_process.terminate()
                        download_process.wait(timeout=3)
                    except:
                        pass
                
                # Jika masih berjalan, gunakan kill sebagai upaya terakhir
                if download_process.poll() is None:
                    try:
                        download_process.kill()
                    except:
                        pass
            
            print_log("Download dihentikan")
            download_process = None
            # PENTING: Jangan ubah download_status menjadi False di sini
            # Biarkan status tetap True agar proses streaming bisa berlanjut
        else:
            print_log("Tidak ada proses download untuk dihentikan.")
    except Exception as e:
        print_log(f"Error: {str(e)}")

def start_streaming(video_file_path, rtmp_url, account_name=None):
    """Memulai proses streaming dari file video ke RTMP URL"""
    global streaming_process, streaming_status, reconnect_attempts
    streaming_status = True
    reconnect_attempts = 0
    
    if not os.path.isfile(video_file_path):
        print_log(f"File video tidak ditemukan: {video_file_path}")
        return False
    
    if account_name:
        print_log(f"Streaming dimulai untuk akun: {account_name}")
    else:
        print_log("Streaming dimulai")
    print_log(f"Streaming file: {video_file_path}")
    print_log(f"Ke URL RTMP: {rtmp_url}")
    
    # Perintah FFmpeg untuk streaming
    ffmpeg_command = [
        FFMPEG_PATH,
        "-re",
        "-stream_loop", "-1",
        "-threads", "4",
        "-i", video_file_path,
        "-c", "copy",
        "-fflags", "+genpts",
        "-rtmp_live", "live",
        "-rtmp_conn", "S:OK",
        "-rtmp_flashver", "FMLE/3.0",
        "-use_wallclock_as_timestamps", "1",
        "-f", "flv",
        rtmp_url
    ]
    
    try:
        cmd_str = " ".join(ffmpeg_command)
        print_log(f"Menjalankan: {cmd_str}")
        streaming_process = subprocess.Popen(
            ffmpeg_command, 
            stderr=subprocess.PIPE, 
            stdout=subprocess.PIPE,
            stdin=subprocess.PIPE,
            text=True,
            creationflags=SUBPROCESS_CREATE_NO_WINDOW
        )
        print_log(f"Proses streaming dimulai dengan PID: {streaming_process.pid}")
        
        def read_stderr():
            while streaming_status and streaming_process and streaming_process.poll() is None:
                try:
                    line = streaming_process.stderr.readline().strip()
                    if line:
                        if any(err in line for err in [
                            "Error", "error", "Failed", "failed", "Connection timed out", 
                            "Error writing header", "Connection refused", "Invalid argument",
                            "Server error"
                        ]):
                            print_log(f"Error streaming terdeteksi: {line}")
                        elif "End of file" in line:
                            print_log("Akhir file terdeteksi, akan memulai ulang streaming...")
                except:
                    pass
                time.sleep(0.1)
        
        stderr_thread = threading.Thread(target=read_stderr)
        stderr_thread.daemon = True
        stderr_thread.start()
        
        print_log("Streaming sedang berjalan...")
        print_log("Tekan Ctrl+C untuk menghentikan streaming")
        
        try:
            while streaming_status and streaming_process and streaming_process.poll() is None:
                time.sleep(1)
        except KeyboardInterrupt:
            print_log("Streaming dihentikan oleh pengguna")
            stop_streaming()
        
        if streaming_process and streaming_process.poll() is not None:
            exit_code = streaming_process.poll()
            print_log(f"Streaming berhenti dengan kode: {exit_code}")
            if exit_code != 0 and streaming_status:
                print_log("Streaming berhenti dengan error, mencoba restart...")
                return start_streaming(video_file_path, rtmp_url, account_name)  # Rekursif restart
        return True
    except Exception as e:
        print_log(f"Error saat memulai streaming: {str(e)}")
        import traceback
        print_log(traceback.format_exc())
        streaming_status = False
        return False

def stop_streaming():
    """Menghentikan proses streaming"""
    global streaming_process, streaming_status, auto_reconnect
    streaming_status = False
    auto_reconnect = False
    print_log("Menghentikan streaming...")
    
    try:
        if streaming_process is not None:
            pid_to_kill = None
            
            if hasattr(streaming_process, 'pid'):
                pid_to_kill = streaming_process.pid
                print_log(f"Menghentikan proses dengan PID: {pid_to_kill}")
            
                # Metode cepat: coba kill langsung dulu
                try:
                    streaming_process.kill()
                    print_log("Proses streaming dimatikan")
                except Exception:
                    pass
            
            # Reset variabel
            streaming_process = None
            print_log("Streaming telah dihentikan")
        else:
            print_log("Tidak ada proses streaming untuk dihentikan.")
    except Exception as e:
        print_log(f"Error saat menghentikan streaming: {str(e)}")

def handle_keyboard_interrupt():
    """Menangani keyboard interrupt (Ctrl+C)"""
    global streaming_process, download_process
    
    print_log("\nProgram dihentikan. Membersihkan proses...")
    
    # Hentikan semua proses yang mungkin masih berjalan
    if streaming_process and hasattr(streaming_process, 'poll') and streaming_process.poll() is None:
        try:
            streaming_process.kill()
            print_log("Proses streaming dihentikan")
        except Exception:
            pass
            
    if download_process and hasattr(download_process, 'poll') and download_process.poll() is None:
        try:
            download_process.kill()
            print_log("Proses download dihentikan")
        except Exception:
            pass
    
    # Bersihkan file sementara
    clear_temp_files()
    
    print_log("Program selesai.")
    sys.exit(0)

def interactive_mode():
    """Mode interaktif untuk menjalankan proses secara berurutan"""
    try:
        print("\n=== LOGIN SHOPEE CLI ===")
        username = input("Username: ")
        password = input("Password: ")
        # Cek login
        if username not in ALLOWED_USERS or ALLOWED_USERS[username] != password:
            print("Login gagal! Username atau password salah.")
            sys.exit(1)
        print("Login berhasil!\n")
        # ...lanjut proses seperti biasa...
        print("\n" + "="*50)
        print("SHOPEE LIVE STREAMING - MODE INTERAKTIF")
        print("="*50)
        
        # Periksa jika tqdm tersedia, jika tidak, install
        if not TQDM_AVAILABLE:
            print_log("Library tqdm tidak tersedia. Mencoba menginstall...")
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", "tqdm"])
                print_log("tqdm berhasil diinstall.")
                # Import ulang setelah install
                try:
                    from tqdm import tqdm
                    globals()['TQDM_AVAILABLE'] = True
                except ImportError:
                    pass
            except Exception as e:
                print_log(f"Gagal menginstall tqdm: {str(e)}. Progress bar sederhana akan digunakan.")
        
        # Tanya apakah ingin membersihkan log
        print("\nApakah Anda ingin membersihkan log? (y/n): ")
        clear_log_choice = input().strip().lower()
        if clear_log_choice == 'y':
            clear_logs(force=True)
            print_log("Log dibersihkan oleh pengguna")
        
        # 1. Input nama akun
        account_name = input("\nMasukkan nama akun Shopee: ")
        print_log(f"Akun: {account_name}")
        
        # 2. Input cookie
        print("\nMasukkan cookie Shopee (paste disini):")
        cookie_string = input()
        print_log(f"Cookie berhasil dimasukkan ({len(cookie_string)} karakter)")
        
        # 3a. Dapatkan session
        print_log("Mendapatkan session ID...")
        session_data = check_session(cookie_string)
        
        if not session_data or 'data' not in session_data or 'list' not in session_data['data'] or len(session_data['data']['list']) == 0:
            print_log("ERROR: Tidak dapat mendapatkan data session. Periksa cookie Anda.")
            return
            
        session_id = session_data['data']['list'][0].get('sessionId', None)
        if not session_id:
            print_log("ERROR: ID sesi tidak ditemukan.")
            return
            
        print_log(f"Session ID berhasil didapatkan: {session_id}")
        
        # 3b. Dapatkan RTMP
        print_log("Mendapatkan URL RTMP...")
        push_urls = get_data_live(session_id, cookie_string)
        
        if not push_urls:
            print_log("ERROR: Tidak dapat mendapatkan URLs. Periksa session ID dan cookie Anda.")
            return
            
        filtered_urls = [url for url in push_urls if
                       not re.search(r'rtmp://\d+\.\d+\.\d+\.\d+/', url) and 'srtrtmp' not in url]
        
        if not filtered_urls:
            print_log("ERROR: Tidak ada RTMP URL yang ditemukan.")
            return
            
        rtmp_url = filtered_urls[0]
        print_log(f"RTMP URL berhasil didapatkan: {rtmp_url}")
        
        # 3c. Dapatkan link download (streaming URL)
        print_log("Mendapatkan URL streaming FLV...")
        streaming_url, response_data = get_streaming_url(session_id, cookie_string)
        
        if not streaming_url:
            print_log("ERROR: Tidak dapat mendapatkan URL streaming.")
            return
            
        print_log(f"URL streaming berhasil didapatkan: {streaming_url}")
        
        # Tampilkan informasi tambahan
        if isinstance(response_data, dict) and 'data' in response_data:
            data = response_data['data']
            if 'sessionTitle' in data:
                print_log(f"Judul: {data['sessionTitle']}")
            if 'sessionStatus' in data:
                status = "Aktif" if data['sessionStatus'] == 1 else "Tidak Aktif"
                print_log(f"Status: {status}")
        
        # 3d. Tanya berapa menit durasi download
        while True:
            try:
                duration_input = input("\nBerapa menit durasi download (default 20): ")
                if duration_input.strip() == "":
                    duration_minutes = 20
                    break
                duration_minutes = int(duration_input)
                if duration_minutes <= 0:
                    print("Durasi harus lebih dari 0 menit!")
                    continue
                break
            except ValueError:
                print("Masukkan angka yang valid!")
        
        print_log(f"Durasi download diatur: {duration_minutes} menit")
        
        # Tanya apakah ingin langsung streaming setelah download
        print("\nApakah Anda ingin langsung streaming setelah download? (y/n): ")
        auto_stream = input().strip().lower() == 'y'
        
        # 3e. Download video
        print_log("Memulai proses download...")
        video_file = download_flv(streaming_url, duration_minutes)
        
        # Cek apakah file berhasil diunduh atau mencari file yang sudah ada
        if video_file is None:
            print_log("Mencari file yang mungkin sudah diunduh sebelumnya...")
            # Coba cari file yang mungkin sudah diunduh
            download_dir = "downloaded_videos"
            if os.path.exists(download_dir):
                # Cari file terbaru di direktori download
                files = [os.path.join(download_dir, f) for f in os.listdir(download_dir) if f.endswith('.flv')]
                if files:
                    # Ambil file terbaru berdasarkan waktu modifikasi
                    video_file = max(files, key=os.path.getmtime)
                    print_log(f"Menggunakan file yang sudah ada: {video_file}")
        
        # Jika masih tidak ada file, keluar
        if not video_file:
            print_log("ERROR: Tidak ada file video untuk streaming.")
            if auto_stream:
                print_log("Streaming tidak dapat dimulai karena tidak ada file video.")
            return
        
        # 3f. Auto mulai streaming setelah download selesai
        print_log(f"File siap: {video_file}")
        
        if auto_stream:
            print_log("="*50)
            print_log("MEMULAI PROSES STREAMING")
            print_log("="*50)
            # Mulai streaming tanpa konfirmasi tambahan
            streaming_result = start_streaming(video_file, rtmp_url, account_name)
            if streaming_result:
                print_log("Streaming berhasil dimulai")
            else:
                print_log("ERROR: Gagal memulai streaming")
        else:
            print_log("Download selesai. Streaming tidak dimulai (sesuai pilihan pengguna).")
            print_log("Program selesai.")
        
    except KeyboardInterrupt:
        handle_keyboard_interrupt()
    except Exception as e:
        print_log(f"Error: {str(e)}")
        import traceback
        print_log(traceback.format_exc())
    finally:
        print_log("Program selesai.")

if __name__ == "__main__":
    # Cek FFmpeg
    if os.path.exists(FFMPEG_PATH):
        print_log(f"FFmpeg ditemukan: {FFMPEG_PATH}")
    else:
        print_log("Menggunakan FFmpeg dari PATH sistem")
    
    # Bersihkan file sementara sebelum memulai
    clear_temp_files()
    
    # Jalankan mode interaktif
    interactive_mode()
