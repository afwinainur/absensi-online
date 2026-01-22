import streamlit as st
import pandas as pd
from datetime import datetime
from pyairtable import Api
import io

# Konfigurasi Halaman
st.set_page_config(page_title="Sistem Rekap Absensi", page_icon="📅", layout="wide")

# --- KONEKSI KE AIRTABLE ---
def get_table():
    try:
        api_key = st.secrets["airtable"]["api_key"]
        base_id = st.secrets["airtable"]["base_id"]
        table_name = "Absensi"
        api = Api(api_key)
        table = api.table(base_id, table_name)
        return table
    except Exception as e:
        st.error(f"❌ Error Koneksi Airtable: {e}")
        return None

# --- FUNGSI UTAMA ---

def load_data():
    """Memuat data dari Airtable dengan penanganan error kolom kosong."""
    try:
        table = get_table()
        if not table:
            return pd.DataFrame()
            
        records = table.all()
        data = [r['fields'] for r in records]
        df = pd.DataFrame(data)
        
        required_cols = ['Tanggal', 'Waktu', 'Nama', 'Aksi', 'Status', 'Keterangan']
        
        # Jika DataFrame kosong (belum ada data sama sekali)
        if df.empty:
            return pd.DataFrame(columns=required_cols)
        
        # Lengkapi kolom yang hilang dengan "-"
        for col in required_cols:
            if col not in df.columns:
                df[col] = "-"
                
        # Pastikan kita hanya mengambil kolom yang dibutuhkan
        return df[required_cols]
        
    except Exception as e:
        st.error(f"⚠️ Gagal memuat data: {e}")
        # Return dataframe kosong agar aplikasi tidak crash total
        return pd.DataFrame(columns=['Tanggal', 'Waktu', 'Nama', 'Aksi', 'Status', 'Keterangan'])

def save_data(new_entry):
    try:
        table = get_table()
        if table:
            # typecast=True penting agar Airtable tidak rewel soal format
            table.create(new_entry, typecast=True)
            return True
        return False
    except Exception as e:
        st.error(f"❌ Gagal menyimpan: {e}")
        return False

def generate_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Sheet1')
    return output.getvalue()

def process_daily_recap(df):
    """Fungsi Rekapitulasi 'Anti-Peluru' (Error Proof)"""
    if df.empty:
        return pd.DataFrame()

    try:
        # 1. BERSIHKAN TANGGAL (Penyebab utama AttributeError)
        # Paksa ubah ke datetime. Jika gagal (misal "-"), jadi NaT (Not a Time)
        df['Tanggal'] = pd.to_datetime(df['Tanggal'], errors='coerce')
        
        # Buang baris yang tanggalnya rusak/kosong
        df = df.dropna(subset=['Tanggal'])
        
        # Jika setelah dibersihkan datanya habis, return kosong
        if df.empty:
            return pd.DataFrame()

        # Ambil tanggalnya saja (aman karena sudah pasti format tanggal)
        df['Tanggal_Only'] = df['Tanggal'].dt.date
        
        rekap_list = []
        
        # Grouping berdasarkan Tanggal yang sudah bersih
        grouped = df.groupby(['Tanggal_Only', 'Nama'])
        
        for (tanggal, nama), group in grouped:
            # Cari Jam Masuk (Min)
            check_in_data = group[group['Aksi'] == 'Check In']
            jam_masuk = "-"
            if not check_in_data.empty:
                # Ambil jam terkecil, ubah ke string
                jam_masuk = str(check_in_data['Waktu'].min())

            # Cari Jam Keluar (Max)
            check_out_data = group[group['Aksi'] == 'Check Out']
            jam_keluar = "-"
            if not check_out_data.empty:
                jam_keluar = str(check_out_data['Waktu'].max())
            
            # Status Terakhir
            status_terakhir = "-"
            if 'Status' in group.columns and not group['Status'].empty:
                status_terakhir = str(group['Status'].iloc[-1])
            
            # Keterangan
            ket_str = "-"
            if 'Keterangan' in group.columns:
                # Gabung keterangan unik, hindari nan/None
                ket_uniq = set([str(k) for k in group['Keterangan'].unique() if str(k) not in ["-", "nan", "None", ""]])
                if ket_uniq:
                    ket_str = ", ".join(ket_uniq)
            
            # Logika Ceklis
            ceklis_in = "❌"
            ceklis_out = "❌"
            
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
                'Keterangan': ket_str
            })
            
        return pd.DataFrame(rekap_list)
        
    except Exception as e:
        # Tampilkan error spesifik jika rekap gagal, tapi jangan crash aplikasinya
        st.error(f"⚠️ Gagal mengolah rekap: {e}")
        return pd.DataFrame()

# --- APLIKASI UTAMA ---

def main():
    try:
        st.title("📅 Absensi KKN - Online")
        
        # Load data
        df_existing = load_data()
        
        # Ambil nama unik
        existing_names = []
        if not df_existing.empty and 'Nama' in df_existing.columns:
            # Pastikan nama diubah ke string dulu sebelum di-sort
            raw_names = df_existing['Nama'].dropna().unique().tolist()
            existing_names = sorted([str(n) for n in raw_names if str(n) not in ["-", "nan", ""]])

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
                            st.rerun()

        # View Data
        df_raw = load_data()
        
        tab1, tab2 = st.tabs(["Rekap Harian", "Raw Data"])
        
        with tab1:
            if not df_raw.empty:
                tgl = st.date_input("Filter Tanggal", datetime.now().date())
                df_rekap = process_daily_recap(df_raw)
                if not df_rekap.empty:
                    # Pastikan kolom Tanggal di df_rekap tipenya date agar bisa dibandingkan
                    show = df_rekap[df_rekap['Tanggal'] == tgl]
                    st.dataframe(show, use_container_width=True)
                    
                    exc = generate_excel(show)
                    st.download_button("Download Excel", exc, f"Rekap_{tgl}.xlsx")
                else:
                    st.info("Belum ada rekap (Data mungkin kosong atau format tanggal salah).")
                    
        with tab2:
            st.dataframe(df_raw, use_container_width=True)
            
    except Exception as e:
        # INI PENTING: Menangkap error utama dan menampilkannya di layar
        st.error("Terjadi Kesalahan Sistem:")
        st.exception(e)

if __name__ == "__main__":
    main()

