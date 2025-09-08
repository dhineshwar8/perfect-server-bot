import os
import discord
from discord.ext import commands
import google.generativeai as genai
from supabase import create_client
from flask import Flask
import threading
from dotenv import load_dotenv

load_dotenv()

# ====== Load secrets ======
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# ====== Configure Gemini ======
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.0-flash")

# ====== Configure Supabase ======
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ====== Configure Discord Bot ======
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ====== Flask Keep Alive ======
app = Flask('')

@app.route('/')
def home():
    return "✅ Discord Bot is running!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    thread = threading.Thread(target=run)
    thread.start()

# ====== Events ======
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    guild_id = str(message.guild.id)

    # Save all user messages into Supabase
    try:
        supabase.table("chat_history").insert({
            "guild_id": guild_id,
            "author": message.author.name,
            "content": message.content
        }).execute()
        print("✅ Saved to Supabase")
    except Exception as e:
        print(f"⚠️ Supabase insert error: {e}")

    # If bot is mentioned → query Supabase + respond
    if bot.user.mentioned_in(message):
        print("🤖 Bot was mentioned!")

        try:
            # Fetch *all* history for this server
            history = supabase.table("chat_history") \
                .select("author,content") \
                .eq("guild_id", guild_id) \
                .order("created_at", desc=False) \
                .execute()

            conversation = [
                f"{row['author']}: {row['content']}" for row in history.data
            ]

            prompt = (
                "You are a helpful Discord bot. "
                "Use the following server chat history as knowledge base to answer questions.\n\n"
                + "\n".join(conversation[-200:])  # limit to last 200 messages to avoid overload
                + f"\n\nNow answer {message.author.name}'s latest question: {message.content}\nBot:"
            )

            response = model.generate_content(prompt)
            reply = response.text if response and response.text else "🤖 (No response generated)"
        except Exception as e:
            reply = f"⚠️ Error while generating response: {e}"

        await message.channel.send(reply)

    await bot.process_commands(message)

# ====== Commands ======
@bot.command()
async def clear(ctx):
    """Clear all chat history for this server"""
    guild_id = str(ctx.guild.id)
    supabase.table("chat_history").delete().eq("guild_id", guild_id).execute()
    await ctx.send("🧹 Chat history cleared!")

# ====== Start Bot ======
keep_alive()
bot.run(DISCORD_TOKEN)
