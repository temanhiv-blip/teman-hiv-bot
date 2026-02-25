import logging
import os
import json
import tempfile
import asyncio
from datetime import datetime, timedelta, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# =========================
# LOGGING
# =========================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =========================
# ENV
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_GROUP_ID = int(os.getenv("ADMIN_GROUP_ID"))
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")

def is_admin_group(update: Update):
    return update.effective_chat and update.effective_chat.id == ADMIN_GROUP_ID
    
# =========================
# GOOGLE SHEETS
# =========================
client = None
sheet_main = None

try:
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    google_creds_env = os.getenv("GOOGLE_CREDENTIALS")

    if google_creds_env:
        creds_dict = json.loads(google_creds_env)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as temp_file:
            json.dump(creds_dict, temp_file)
            temp_creds_path = temp_file.name

        creds = ServiceAccountCredentials.from_json_keyfile_name(temp_creds_path, scope)
        os.unlink(temp_creds_path)

        client = gspread.authorize(creds)
        ss = client.open_by_key(SPREADSHEET_ID)
        sheet_main = ss.worksheet("Konsultasi")

        logger.info("✅ Connected to Google Sheets")

except Exception as e:
    logger.error(f"❌ Sheets Error: {e}")

# =========================
# MENU
# =========================
def menu_utama_keyboard():
    keyboard = [
        [InlineKeyboardButton("ℹ️ Panduan Layanan", callback_data="panduan")],
        [InlineKeyboardButton("📋 Tatakunan Umum", callback_data="tatakunan_umum")],
        [InlineKeyboardButton("📋 Cek Risiko HIV", callback_data="cek_risiko")],
        [InlineKeyboardButton("📨 Kirim Tatakunan", callback_data="kirim_tatakunan")],
        [InlineKeyboardButton("💬 Chat dengan Admin", callback_data="chat_admin_info")],
        [InlineKeyboardButton("📚 Media Edukasi", callback_data="media_edukasi")]
    ]
    return InlineKeyboardMarkup(keyboard)

# =========================
# DATA DINAMIS
# =========================
async def get_faq_text():
    try:
        ws = client.open_by_key(SPREADSHEET_ID).worksheet("FAQ")
        records = ws.get_all_records()
        if not records:
            return "Data FAQ kosong."
        teks = "📑 *Tatakunan Umum (FAQ)*\n\n"
        for r in records:
            teks += f"❓ *{r['Pertanyaan']}*\n_{r['Jawaban']}_\n\n"
        return teks
    except:
        return "⚠️ Gagal mengambil FAQ."

async def get_admin_markup(alias, usia):
    try:
        ws = client.open_by_key(SPREADSHEET_ID).worksheet("Admin")
        records = ws.get_all_records()
        keyboard = []
        msg = f"Halo, saya {alias} ({usia} tahun) ingin konsultasi HIV."
        msg_enc = msg.replace(" ", "%20")

        for r in records:
            if str(r["Status"]).lower() == "aktif":
                if r["Tipe"] == "Telegram":
                    url = f"https://t.me/{r['Kontak']}?text={msg_enc}"
                else:
                    url = f"https://wa.me/{r['Kontak']}?text={msg_enc}"
                keyboard.append([InlineKeyboardButton(f"📱 {r['Nama']} ({r['Tipe']})", url=url)])

        keyboard.append([InlineKeyboardButton("⬅️ Kembali", callback_data="kembali_menu")])
        return InlineKeyboardMarkup(keyboard)
    except:
        return None

async def get_risk_questions():
    try:
        ws = client.open_by_key(SPREADSHEET_ID).worksheet("Pertanyaan_Risiko")
        return [r["Pertanyaan"] for r in ws.get_all_records() if r["Pertanyaan"]]
    except:
        return []

async def get_media_edukasi():
    try:
        ws = client.open_by_key(SPREADSHEET_ID).worksheet("Media_Edukasi")
        records = ws.get_all_records()
        if not records:
            return "Data Media Edukasi kosong.", None

        teks = "📚 *Media Edukasi HIV*\n\n"
        keyboard = []

        for r in records:
            if r.get("Status", "").lower() == "aktif":
                teks += f"📄 *{r['Judul']}*\n_{r['Deskripsi']}_\n\n"
                keyboard.append([InlineKeyboardButton(f"🔗 {r['Judul']}", url=r["Link"])])

        keyboard.append([InlineKeyboardButton("⬅️ Kembali", callback_data="kembali_menu")])
        return teks, InlineKeyboardMarkup(keyboard)
    except:
        return "⚠️ Gagal mengambil media.", None

# =========================
# START
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["mode"] = "input_alias"
    await update.message.reply_text(
        "👋 *Salamat Datang di TemanHIV*\n"
        "_Layanan Konsultasi HIV oleh KPAD Kabupaten_\n\n"
        "TemanHIV membantu pian memperoleh informasi HIV secara aman, rahasia, dan terpercaya.\n\n"
        "Pian dapat menggunakan nama samaran.\n\n"
        "Silakan tulis nama samaran pian untuk memulai:",
        parse_mode=ParseMode.MARKDOWN
    )

# =========================
# USER MESSAGE
# =========================
async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = context.user_data.get("mode")
    text = update.message.text.strip()

    if mode == "input_alias":
        context.user_data["alias"] = text
        context.user_data["mode"] = "pilih_alamat"

        keyboard = [[InlineKeyboardButton(k, callback_data=f"alamat_{k}")]
                    for k in ["Paringin", "Paringin Selatan", "Awayan", "Batu Mandi",
                              "Lampihong", "Juai", "Halong", "Luar Wilayah"]]

        await update.message.reply_text(
            f"Halo *{text}*, pilih kecamatan pian:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )

    elif mode == "input_usia":
        if text.isdigit():
            context.user_data["usia"] = text
            context.user_data["mode"] = None
            await update.message.reply_text(
                f"Data tersimpan!\n👤 {context.user_data['alias']}\n🎂 {text} tahun",
                reply_markup=menu_utama_keyboard(),
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await update.message.reply_text("Usia harus angka.")

    elif mode == "kirim_tatakunan":

        alias = context.user_data.get("alias")
        usia = context.user_data.get("usia")
        alamat = context.user_data.get("alamat")
        user_id = str(update.effective_user.id)
    
        # 🔒 VALIDASI SESSION
        if not alias or not usia or not alamat:
            context.user_data.clear()
            context.user_data["mode"] = "input_alias"
    
            await update.message.reply_text(
                "⚠️ Sesi pian telah berakhir atau data belum lengkap.\n\n"
                "Silakan isi kembali nama samaran pian:"
            )
            return
    
        wita = timezone(timedelta(hours=8))
        now_dt = datetime.now(wita)
        waktu = now_dt.strftime("%Y-%m-%d %H:%M:%S")
    
        # =========================================
        # 🔍 CEK APAKAH ADA TIKET PENDING
        # =========================================
        existing_ticket = None
        existing_row_number = None
    
        if sheet_main:
            rows = sheet_main.get_all_values()
            for idx, row in enumerate(rows[1:], start=2):  # skip header
                if len(row) > 10:
                    if row[10] == user_id and row[8] == "Pending":
                        existing_ticket = row
                        existing_row_number = idx
                        break
    
        # =========================================
        # 📝 JIKA ADA TIKET PENDING → APPEND
        # =========================================
        if existing_ticket:
    
            kode = existing_ticket[5]
            isi_lama = existing_ticket[3]
    
            tambahan = f"+ ({waktu}) {text}"
            isi_baru = f"{isi_lama}\n\n{tambahan}"
    
            # Update kolom D (Pertanyaan)
            sheet_main.update(
                range_name=f"D{existing_row_number}",
                values=[[isi_baru]]
            )
    
            # Notifikasi ke admin
            await context.bot.send_message(
                chat_id=ADMIN_GROUP_ID,
                text=(
                    f"📝 *Tambahan Tatakunan*\n"
                    f"🆔 `{kode}`\n"
                    f"👤 {alias}\n\n"
                    f"{tambahan}"
                ),
                parse_mode=ParseMode.MARKDOWN
            )
    
            await update.message.reply_text(
                f"📝 Tambahan berhasil dikirim ke tiket 🆔 {kode}.\n"
                "Admin akan membalas setelah tiket diproses."
            )
    
            context.user_data["mode"] = None
            return
    
        # =========================================
        # 📨 JIKA TIDAK ADA → BUAT TIKET BARU
        # =========================================
    
        kode = f"K{int(datetime.now().timestamp())}"
    
        text_admin = (
            f"📨 *Tatakunan Baru*\n"
            f"👤 {alias} ({usia} thn)\n"
            f"📍 {alamat}\n"
            f"🆔 `{kode}`\n\n{text}"
        )
    
        btn = [[
            InlineKeyboardButton(
                "💬 Balas",
                callback_data=f"balas_{user_id}_{kode}"
            )
        ]]
    
        await context.bot.send_message(
            chat_id=ADMIN_GROUP_ID,
            text=text_admin,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(btn)
        )
    
        if sheet_main:
            sheet_main.append_row([
                waktu,
                alias,
                usia,
                text,
                "",
                kode,
                "",
                alamat,
                "Pending",
                "",
                user_id
            ])
    
        await update.message.reply_text(
            f"✅ Tatakunan terkirim.\n🆔 Kode tiket pian: {kode}"
        )
    
        context.user_data["mode"] = None
    
        await update.message.reply_text(
            "Pilih menu lainnya:",
            reply_markup=menu_utama_keyboard()
        )

# =========================
# CALLBACK
# =========================
async def tombol_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == "panduan":
        teks = (
            "ℹ️ *Panduan Layanan TemanHIV – KPAD Kabupaten*\n\n"
            "TemanHIV adalah layanan konsultasi HIV yang dikelola oleh "
            "KPAD Kabupaten untuk membantu masyarakat memperoleh informasi yang benar, aman, dan rahasia.\n\n"
            "🔹 Pian dapat menggunakan nama samaran.\n"
            "🔹 Data dan percakapan dijaga kerahasiaannya.\n"
            "🔹 Sistem menggunakan tiket (1 tiket untuk 1 pertanyaan).\n"
            "🔹 Balasan admin dikirim langsung ke akun Telegram pian.\n\n"
            "⏳ Layanan dapat diakses 24 jam.\n"
            "Balasan diprioritaskan pada jam kerja\n"
            "Senin–Jumat, 08.00–16.00 WITA.\n\n"
            "Jika dalam kondisi darurat medis, segera hubungi fasilitas kesehatan terdekat.\n\n"
            "Terima kasih telah mempercayakan layanan ini."
        )

        await query.edit_message_text(
            teks,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ Kembali", callback_data="kembali_menu")]]
            )
        )
        return
    elif data == "tatakunan_umum":
        teks = await get_faq_text()
        await query.edit_message_text(
            teks,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Kembali", callback_data="kembali_menu")]])
        )
        
    elif data.startswith("plist_"):
        page = int(data.split("_")[1])
        context.args = [str(page)]
        await list_pending(update, context)
        
    elif data == "kembali_menu":
        await query.edit_message_text(
            "🌟 *Menu Utama*\nSilakan pilih layanan:",
            reply_markup=menu_utama_keyboard(),
            parse_mode=ParseMode.MARKDOWN
        )

    elif data.startswith("alamat_"):
        context.user_data["alamat"] = data.replace("alamat_", "")
        context.user_data["mode"] = "input_usia"
        await query.edit_message_text("Berapa usia pian saat ini?")
        
    elif data == "kirim_tatakunan":

        alias = context.user_data.get("alias")
        usia = context.user_data.get("usia")
        alamat = context.user_data.get("alamat")
    
        # 🔒 VALIDASI IDENTITAS
        if not alias or not usia or not alamat:
            context.user_data.clear()
            context.user_data["mode"] = "input_alias"
        
            await query.edit_message_text(
                "⚠️ Sesi pian telah berakhir.\n\n"
                "Silakan isi kembali nama samaran pian:"
            )
            return
    
        context.user_data["mode"] = "kirim_tatakunan"
    
        await query.edit_message_text(
            "📨 *Kirim Tatakunan*\n\n"
            "Sistem ini menggunakan sistem tiket konsultasi.\n\n"
            "🔹 1 tiket hanya untuk 1 pertanyaan.\n"
            "🔹 Jika memiliki pertanyaan lain, silakan membuat tiket baru setelah pertanyaan sebelumnya dibalas.\n"
            "🔹 Mohon tidak mengirim pesan berulang untuk pertanyaan yang sama.\n\n"
            "Balasan akan dikirim secara pribadi ke akun Telegram pian.\n\n"
            "Silakan tuliskan pertanyaan pian dengan jelas dan lengkap.",
            parse_mode=ParseMode.MARKDOWN
        )
    elif data == "chat_admin_info":

        teks = (
            "💬 *Chat Langsung dengan Admin*\n\n"
            "Dengan memilih menu ini:\n\n"
            "🔹 Pian akan terhubung langsung ke akun pribadi admin.\n"
            "🔹 Identitas Telegram atau WhatsApp pian akan terlihat oleh admin.\n"
            "🔹 Admin menjaga kerahasiaan sesuai etika layanan KPAD Kabupaten.\n\n"
            "Jika ingin tetap menggunakan nama samaran, silakan gunakan menu *Kirim Tatakunan*.\n\n"
            "Apakah pian ingin melanjutkan?"
        )

        keyboard = [
            [InlineKeyboardButton("✅ Lanjutkan", callback_data="chat_admin")],
            [InlineKeyboardButton("⬅️ Kembali", callback_data="kembali_menu")]
        ]

        await query.edit_message_text(
            teks,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
        
    elif data == "chat_admin":
        alias = context.user_data.get("alias")
        usia = context.user_data.get("usia")
        if not alias or not usia:
            await query.edit_message_text("⚠️ Data belum lengkap. Silakan /start ulang.")
            return
        markup = await get_admin_markup(alias, usia)
        await query.edit_message_text("💬 Hubungi Admin via:", reply_markup=markup)

    elif data == "media_edukasi":
        teks, markup = await get_media_edukasi()
        await query.edit_message_text(teks, parse_mode=ParseMode.MARKDOWN, reply_markup=markup)

    elif data == "cek_risiko":
        questions = await get_risk_questions()
        if not questions:
            await query.edit_message_text("Pertanyaan risiko belum tersedia.")
            return
        context.user_data["questions"] = questions
        context.user_data["skor"] = 0
        context.user_data["idx"] = 0
        await query.edit_message_text(
            f"❓ {questions[0]}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Ya", callback_data="res_ya"),
                 InlineKeyboardButton("Tidak", callback_data="res_no")]
            ])
        )

    elif data.startswith("res_"):
        if data == "res_ya":
            context.user_data["skor"] += 1
        context.user_data["idx"] += 1
        idx = context.user_data["idx"]
        questions = context.user_data["questions"]

        if idx < len(questions):
            await query.edit_message_text(
                f"❓ {questions[idx]}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Ya", callback_data="res_ya"),
                     InlineKeyboardButton("Tidak", callback_data="res_no")]
                ])
            )
        else:
            skor = context.user_data["skor"]
            hasil = "❗Pian Risiko Tinggi (Segera Tes & Konsultasi Admin)" if skor >= 3 else "✅ Resiko Pian Rendah, Tetap Pertahankan"
        
            # ✅ SIMPAN KE SHEET RISIKO
            try:
                wita = timezone(timedelta(hours=8))
                now = datetime.now(wita).strftime("%Y-%m-%d %H:%M:%S")
        
                rs_sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Risiko")
        
                rs_sheet.append_row([
                    now,
                    context.user_data.get("alias"),
                    context.user_data.get("usia"),
                    skor,
                    hasil,
                    context.user_data.get("alamat")
                ])
            except Exception as e:
                logger.error(f"Gagal simpan risiko: {e}")
        
            await query.edit_message_text(
                f"Hasil Cek Risiko: *{hasil}* (Skor: {skor})",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("⬅️ Kembali", callback_data="kembali_menu")]]
                )
            )

# =========================
# LOCK TIKET (FINAL FIX)
# =========================
async def handle_balas_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    if not is_admin_group(update):
        return

    try:
        _, user_id, kode = query.data.split("_")
    except:
        await query.message.reply_text("❌ Format tiket salah.")
        return

    admin_user = update.effective_user
    admin_id = str(admin_user.id).strip()
    admin_display = f"@{admin_user.username}" if admin_user.username else admin_user.first_name

    try:
        cell = sheet_main.find(kode, in_column=6)  # kolom F = Kode
        row_number = cell.row
        row = sheet_main.row_values(row_number)
    except:
        await query.message.reply_text("❌ Tiket tidak ditemukan.")
        return

    status = str(row[8]).strip() if len(row) > 8 else ""
    locked_by = str(row[9]).strip() if len(row) > 9 else ""

    if status == "Replied":
        await query.message.reply_text("❌ Tiket sudah dibalas.")
        return

    if status == "Locked" and locked_by and locked_by != admin_id:
        await query.message.reply_text("🔒 Tiket sedang ditangani admin lain.")
        return

    # LOCK
    sheet_main.update(
        range_name=f"I{row_number}:J{row_number}",
        values=[["Locked", admin_id]]
    )

    # 🔔 NOTIFIKASI KE KLIEN BAHWA TIKET DI-LOCK
    try:
        user_id_sheet = str(row[10]).strip() if len(row) > 10 else ""
        if user_id_sheet:
            await context.bot.send_message(
                chat_id=int(user_id_sheet),
                text=(
                    f"🔒 Tatakunan pian dengan kode 🆔 {kode} "
                    "sedang diproses oleh admin.\n\n"
                    "Pian tidak dapat menambahkan pesan lagi ke tiket ini.\n"
                    "Mohon menunggu balasan."
                )
            )
    except Exception as e:
        logger.error(f"Gagal kirim notifikasi lock ke klien: {e}")

    await query.message.reply_text(
        f"🔒 Tiket dikunci oleh {admin_display}\n"
        f"Reply pesan ini untuk membalas kode {kode}."
    )
# =========================
# PROSES BALAS ADMIN (FINAL FIX)
# =========================
async def admin_reply_text(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not is_admin_group(update):
        return

    if not update.message.reply_to_message:
        return

    reply_text = update.message.reply_to_message.text or ""

    if "membalas kode" not in reply_text.lower():
        return

    import re
    match = re.search(r'kode\s+([A-Za-z0-9]+)', reply_text)
    if not match:
        await update.message.reply_text("❌ Kode tidak ditemukan.")
        return

    kode = match.group(1)

    admin_user = update.effective_user
    admin_id = str(admin_user.id).strip()
    admin_display = f"@{admin_user.username}" if admin_user.username else admin_user.first_name
    balasan = update.message.text

    try:
        cell = sheet_main.find(kode, in_column=6)
        row_number = cell.row
        row = sheet_main.row_values(row_number)
    except:
        await update.message.reply_text("❌ Tiket tidak ditemukan.")
        return

    status = str(row[8]).strip() if len(row) > 8 else ""
    locked_by = str(row[9]).strip() if len(row) > 9 else ""
    user_id = str(row[10]).strip() if len(row) > 10 else ""

    if status != "Locked":
        await update.message.reply_text("❌ Tiket belum dikunci.")
        return

    if str(locked_by).strip() != str(admin_id).strip():
        await update.message.reply_text(
            f"❌ Tiket ini dikunci oleh ID {locked_by}, bukan {admin_id}"
        )
        return

    # Kirim ke client
    try:
        await context.bot.send_message(
            chat_id=int(user_id),
            text=f"📬 *Balasan Admin*\n🆔 `{kode}`\n\n{balasan}",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Gagal kirim: {e}")
        return

    # Update sheet → Replied
    sheet_main.update(
        range_name=f"E{row_number}:K{row_number}",
        values=[[
            balasan,
            kode,
            admin_display,
            row[7] if len(row) > 7 else "",
            "Replied",
            "",
            user_id
        ]]
    )
    await update.message.reply_text("✅ Balasan terkirim & status diperbarui.")
# =========================
# LIST PENDING (FIX FINAL)
# =========================
async def list_pending(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not is_admin_group(update):
        return

    target = update.message if update.message else update.callback_query.message

    if not sheet_main:
        await target.reply_text("⚠️ Database belum tersedia.")
        return

    rows = sheet_main.get_all_values()

    if len(rows) <= 1:
        await target.reply_text("📭 Belum ada data.")
        return

    pending_rows = []

    for row in reversed(rows[1:]):  # skip header
        if len(row) > 8 and str(row[8]).strip() == "Pending":
            pending_rows.append(row)

    if not pending_rows:
        await target.reply_text("✅ Tidak ada tiket Pending.")
        return

    await target.reply_text("📋 *Daftar Tiket Pending*", parse_mode=ParseMode.MARKDOWN)

    for row in pending_rows:

        kode = row[5]
        nama = row[1]
        usia = row[2]
        alamat = row[7]
        pertanyaan = row[3]
        user_id = row[10] if len(row) > 10 else ""

        teks = (
            f"🆔 *{kode}*\n"
            f"👤 {nama} ({usia} thn)\n"
            f"📍 {alamat}\n"
            f"❓ {pertanyaan}"
        )

        if user_id:
            btn = [[
                InlineKeyboardButton(
                    "💬 Balas",
                    callback_data=f"balas_{user_id}_{kode}"
                )
            ]]

            await target.reply_text(
                teks,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(btn)
            )
        else:
            await target.reply_text(teks, parse_mode=ParseMode.MARKDOWN)

# =========================
# RUN (AUTO WEBHOOK / POLLING)
# =========================
if __name__ == "__main__":

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # ===== Handlers =====
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("list", list_pending))
    app.add_handler(CallbackQueryHandler(handle_balas_admin, pattern="^balas_"))
    app.add_handler(CallbackQueryHandler(tombol_handler))
    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE, handle_user_message))
    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.GROUPS, admin_reply_text))

    # =========================
    # MODE DETECTION
    # =========================
    PUBLIC_DOMAIN = os.getenv("RAILWAY_PUBLIC_DOMAIN")
    PORT = int(os.getenv("PORT", 8000))

    if PUBLIC_DOMAIN:
        WEBHOOK_URL = f"https://{PUBLIC_DOMAIN}"
        logger.info(f"🚀 Running in WEBHOOK mode: {WEBHOOK_URL}")

        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            webhook_url=WEBHOOK_URL,
        )
    else:
        logger.info("⚠️ Running in POLLING mode (no domain detected)")
        app.run_polling(drop_pending_updates=True)
