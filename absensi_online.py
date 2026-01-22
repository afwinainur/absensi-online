import streamlit as st
import pandas as pd
from datetime import datetime
from pyairtable import Api
import io

# Konfigurasi Halaman
st.set_page_config(page_title="Sistem Rekap Absensi", page_icon="📅", layout="wide")

# --- KONEKSI KE AIRTABLE ---
def get_table():
    # Mengambil credentials dari Streamlit Secrets
    api_key = st.secrets["airtable"]["api_key"]
    base_id = st.secrets["airtable"]["base_id"]
    table_name = "Absensi" # Pastikan nama tabel di Airtable sama persis
    
    api = Api(api_key)
    table = api.table(base_id, table_name)
    return table

# --- FUNGSI UTAMA ---

def load_data():
    """Memuat data dari Airtable."""
    try:
        table = get_table()
        # Mengambil semua data (return list of dicts)
        records = table.all()
        
        # Airtable mengembalikan data dalam format: [{'id':..., 'createdTime':..., 'fields': {DataKita}}]
        # Kita perlu ekstrak bagian 'fields'
        data = [r['fields'] for r in records]
        
        df = pd.DataFrame(data)
        
        # Pastikan kolom urut dan lengkap
        required_cols = ['Tanggal', 'Waktu', 'Nama', 'Aksi', 'Status', 'Keterangan']
        
        if df.empty:
            return pd.DataFrame(columns=required_cols)
        
        # Tambahkan kolom yang hilang jika ada (misal data baru kosong)
        for col in required_cols:
            if col not in df.columns:
                df[col] = "-"
                
        return df[required_cols]
    except Exception as e:
        # st.error(f"Gagal memuat data: {e}") # Debugging
        return pd.DataFrame(columns=['Tanggal', 'Waktu', 'Nama', 'Aksi', 'Status', 'Keterangan'])

def save_data(new_entry):
    """Menyimpan data baru ke Airtable."""
    try:
        table = get_table()
        # Airtable butuh dictionary, new_entry sudah dalam bentuk dict
        table.create(new_entry)
        return True
    except Exception as e:
        st.error(f"Gagal menyimpan ke Airtable: {e}")
        return False

def generate_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Sheet1')
    return output.getvalue()

def process_daily_recap(df):
    if df.empty:
        return pd.DataFrame()

    df['Tanggal'] = pd.to_datetime(df['Tanggal']).dt.date
    rekap_list = []
    
    # Grouping data
    if 'Nama' in df.columns:
        grouped = df.groupby(['Tanggal', 'Nama'])
        
        for (tanggal, nama), group in grouped:
            check_in_data = group[group['Aksi'] == 'Check In']
            jam_masuk = check_in_data['Waktu'].min() if not check_in_data.empty else "-"
            
            check_out_data = group[group['Aksi'] == 'Check Out']
            jam_keluar = check_out_data['Waktu'].max() if not check_out_data.empty else "-"
            
            status_terakhir = group['Status'].iloc[-1]
            
            # Gabung keterangan
            ket_list = [str(k) for k in group['Keterangan'].unique() if k not in ["-", None, "nan"]]
            ket_str = ", ".join(ket_list)
            
            if status_terakhir in ['Izin', 'Sakit']:
                ceklis_in = "❌"
                ceklis_out = "❌"
            else:
                ceklis_in = "✅" if jam_masuk != "-" else "❌"
                ceklis_out = "✅" if jam_keluar != "-" else "❌"
            
            rekap_list.append({
                'Tanggal': tanggal,
                'Nama': nama,
                'Jam Masuk': jam_masuk,
                'Jam Keluar': jam_keluar,
                'Status Kehadiran': status_terakhir,
                'Check In': ceklis_in,
                'Check Out': ceklis_out,
                'Keterangan': ket_str if ket_str else "-"
            })
            
    return pd.DataFrame(rekap_list)

# --- APLIKASI UTAMA ---

def main():
    st.title("📅 Absensi KKN - Online")
    
    # Load data
    df_existing = load_data()
    
    # Ambil nama unik
    existing_names = []
    if not df_existing.empty and 'Nama' in df_existing.columns:
        raw_names = df_existing['Nama'].dropna().unique().tolist()
        existing_names = sorted([n for n in raw_names if n not in ["-", ""]])

    with st.sidebar:
        st.header("📝 Form Input")
        
        nama_final = ""
        pilihan_nama = "-- Pilih Nama --"
        
        if existing_names:
            pilihan_nama = st.selectbox(
                "Cari Nama", 
                options=["-- Pilih Nama --"] + existing_names + ["➕ Input Nama Baru..."]
            )
        
        if not existing_names or pilihan_nama == "➕ Input Nama Baru...":
            nama_final = st.text_input("Nama Lengkap Baru")
        elif pilihan_nama != "-- Pilih Nama --":
            nama_final = pilihan_nama
            
        st.write("---")

        with st.form("absensi_form", clear_on_submit=True):
            status = st.selectbox("Status", ["Hadir", "Izin", "Sakit"])
            aksi = st.radio("Aksi", ["Check In", "Check Out"], horizontal=True)
            ket = st.text_area("Keterangan")
            
            submitted = st.form_submit_button("Kirim Data 🚀")
            
            if submitted:
                if not nama_final:
                    st.error("Nama harus diisi!")
                else:
                    now = datetime.now()
                    # Siapkan data untuk Airtable
                    new_data = {
                        'Tanggal': now.strftime("%Y-%m-%d"),
                        'Waktu': now.strftime("%H:%M:%S"),
                        'Nama': nama_final,
                        'Aksi': aksi,
                        'Status': status,
                        'Keterangan': ket if ket else "-"
                    }
                    
                    if save_data(new_data):
                        st.success("Data berhasil disimpan!")
                        st.experimental_rerun()

    # View Data
    df_raw = load_data()
    
    tab1, tab2 = st.tabs(["Rekap Harian", "Raw Data"])
    
    with tab1:
        if not df_raw.empty:
            tgl = st.date_input("Filter Tanggal", datetime.now().date())
            df_rekap = process_daily_recap(df_raw)
            if not df_rekap.empty:
                show = df_rekap[df_rekap['Tanggal'] == tgl]
                st.dataframe(show, use_container_width=True)
                
                # Download Excel
                exc = generate_excel(show)
                st.download_button("Download Excel", exc, f"Rekap_{tgl}.xlsx")
            else:
                st.info("Belum ada rekap.")
                
    with tab2:
        st.dataframe(df_raw, use_container_width=True)

if __name__ == "__main__":

    main()



