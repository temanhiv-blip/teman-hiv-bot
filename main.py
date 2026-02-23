import logging
import os
import json
import tempfile
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
        [InlineKeyboardButton("📋 Tatakunan Umum", callback_data="tatakunan_umum")],
        [InlineKeyboardButton("📋 Cek Risiko HIV", callback_data="cek_risiko")],
        [InlineKeyboardButton("📨 Kirim Tatakunan", callback_data="kirim_tatakunan")],
        [InlineKeyboardButton("💬 Chat dengan Admin", callback_data="chat_admin")],
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
        "Salamat Datang di *TemanHIV* 👋\nSilakan tulis nama pian (Samaran):",
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
        wita = timezone(timedelta(hours=8))
        waktu = datetime.now(wita).strftime("%Y-%m-%d %H:%M:%S")
        kode = f"K{int(datetime.now().timestamp())}"

        alias = context.user_data.get("alias")
        usia = context.user_data.get("usia")
        alamat = context.user_data.get("alamat")

        text_admin = (
            f"📨 *Tatakunan Baru*\n"
            f"👤 {alias} ({usia} thn)\n"
            f"📍 {alamat}\n"
            f"🆔 `{kode}`\n\n{text}"
        )

        btn = [[InlineKeyboardButton("💬 Balas", callback_data=f"balas_{update.effective_user.id}_{kode}")]]

        await context.bot.send_message(
            chat_id=ADMIN_GROUP_ID,
            text=text_admin,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(btn)
        )

        if sheet_main:
            sheet_main.append_row([
                waktu, alias, usia, text, "", kode, "", alamat, "Pending", update.effective_user.id
            ])

        await update.message.reply_text(f"✅ Terkirim. Kode pian: {kode}")
        context.user_data["mode"] = None
        await update.message.reply_text("Pilih menu lainnya:", reply_markup=menu_utama_keyboard())

# =========================
# CALLBACK
# =========================
async def tombol_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "tatakunan_umum":
        teks = await get_faq_text()
        await query.edit_message_text(
            teks,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Kembali", callback_data="kembali_menu")]])
        )

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
            hasil = "❗ Tinggi (Segera Tes & Konsultasi Admin)" if skor >= 3 else "✅ Rendah"
            await query.edit_message_text(
                f"Hasil Cek Risiko: *{hasil}* (Skor: {skor})",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Kembali", callback_data="kembali_menu")]])
            )

# =========================
# LOCK + BALAS ADMIN
# =========================
async def handle_balas_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    _, user_id, kode = query.data.split("_")
    admin_name = update.effective_user.first_name

    rows = sheet_main.get_all_values()

    for i, row in enumerate(rows):
        if len(row) > 5 and row[5] == kode:
            status = row[8] if len(row) > 8 else ""

            if status == "Replied":
                await query.message.reply_text("❌ Tiket sudah dibalas.")
                return

            if status.startswith("Locked") and admin_name not in status:
                await query.message.reply_text("🔒 Tiket sedang ditangani admin lain.")
                return

            sheet_main.update_cell(i+1, 9, f"Locked by {admin_name}")
            break

    context.user_data["reply_target"] = int(user_id)
    context.user_data["reply_kode"] = kode

    await query.message.reply_text(
        f"🔒 Tiket dikunci oleh {admin_name}\nSilakan ketik balasan untuk kode {kode}:"
    )

async def admin_reply_text(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if "reply_target" not in context.user_data:
        return

    uid = context.user_data["reply_target"]
    kode = context.user_data["reply_kode"]
    admin_name = update.effective_user.first_name
    balasan = update.message.text

    await context.bot.send_message(
        chat_id=uid,
        text=f"📬 *Balasan Admin*\n🆔 `{kode}`\n\n{balasan}",
        parse_mode=ParseMode.MARKDOWN
    )

    rows = sheet_main.get_all_values()

    for i, row in enumerate(rows):
        if len(row) > 5 and row[5] == kode:
            sheet_main.update(
                f"E{i+1}:I{i+1}",
                [[balasan, kode, admin_name, row[7], "Replied"]]
            )
            break

    await update.message.reply_text("✅ Balasan terkirim & status diperbarui.")

    context.user_data.pop("reply_target", None)
    context.user_data.pop("reply_kode", None)

# =========================
# RUN
# =========================
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_balas_admin, pattern="^balas_"))
    app.add_handler(CallbackQueryHandler(tombol_handler))
    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE, handle_user_message))
    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.GROUPS, admin_reply_text))

    logger.info("🤖 Bot Started...")
    app.run_polling(drop_pending_updates=True)
