# Complete code for the bot including media_edukasi handler

from telegram import Update, ForceReply
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

# Function to start the bot


def start(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    update.message.reply_html(
        rf"Hi {user.mention_html()}!\nI'm your educational bot. How can I assist you?",
        reply_markup=ForceReply(selective=True),
    )

# Function to handle media_edukasi

def media_edukasi(update: Update, context: CallbackContext) -> None:
    update.message.reply_text('This is your media edukasi content!')

# Main function to run the bot

def main() -> None:
    # Create Updater and pass it your bot's token
    updater = Updater("<YOUR BOT TOKEN>")

    # Get the dispatcher to register handlers
    dispatcher = updater.dispatcher

    # Add handlers
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, media_edukasi))

    # Start the bot
    updater.start_polling()

    # Run the bot until you send a signal to stop
    updater.idle()

if __name__ == '__main__':
    main()