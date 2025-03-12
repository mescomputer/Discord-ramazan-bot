import discord
from discord.ext import commands, tasks
import aiohttp
import asyncio
import datetime
import json
import os
import unidecode  # Türkçe karakterleri API uyumlu hale getirmek için

# Bot yetkileri (intents)
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.dm_messages = True
intents.message_content = True  # Mesaj içeriklerini okumak için gerekli
intents.members = True  # Üye bilgilerini almak için gerekli

bot = commands.Bot(command_prefix="!!", intents=intents)

# Yetkili kullanıcılar
AUTHORIZED_USERS = {USER ID 1,USER ID 2}

# JSON dosyaları
CACHE_FILE = "cache.json"      # Namaz vakitleri için API sonuçları
USERS_FILE = "users.json"      # DM bildirim abonelikleri (user_id -> city)
SERVERS_FILE = "servers.json"  # Kanal bildirim abonelikleri (guild_id -> { city, channel, ping_role })

# API bilgileri
API_KEY = "Api key "
API_URL_TEMPLATE = "https://api.collectapi.com/pray/all?data.city={}"
headers = {
    "content-type": "application/json",
    "authorization": f"apikey {API_KEY}"
}

# Dosya okuma/yazma fonksiyonları
def load_data(file):
    if os.path.exists(file):
        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_data(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

def turkish_to_english(text):
    return unidecode.unidecode(text.lower())

cache = load_data(CACHE_FILE)
users = load_data(USERS_FILE)
servers = load_data(SERVERS_FILE)

# !!namaz_info → Günlük namaz vakitlerini gösterir.
@bot.command(name="namaz_info")
async def namaz_info(ctx):
    await ctx.send("Bu mesajı yanıtlayarak il seçiniz (örn: Denizli)")
    
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel
    
    try:
        msg = await bot.wait_for('message', check=check, timeout=30)
    except asyncio.TimeoutError:
        await ctx.send("Zaman aşımı, lütfen tekrar deneyin.")
        return

    city = turkish_to_english(msg.content.strip())
    today_str = datetime.date.today().isoformat()

    if city in cache and cache[city]["date"] == today_str:
        prayer_times = cache[city]["data"]["result"]
    else:
        async with aiohttp.ClientSession() as session:
            async with session.get(API_URL_TEMPLATE.format(city), headers=headers) as response:
                if response.status != 200:
                    print(f"API Hatası: {response.status}")
                    await ctx.send("❌ Şehir bulunamadı veya API hatası.")
                    return
                try:
                    data = await response.json()
                    if not data.get("success") or "result" not in data:
                        await ctx.send("❌ Geçersiz veri alındı.")
                        return
                    cache[city] = {"date": today_str, "data": data}
                    save_data(CACHE_FILE, cache)
                    prayer_times = data["result"]
                except Exception as e:
                    print(f"API Yanıt Hatası: {e}")
                    await ctx.send("❌ API yanıtı işlenirken hata oluştu.")
                    return
    
    response_text = f"📌 **{msg.content.capitalize()}** için namaz vakitleri:\n" + "\n".join(
        [f"🕰 **{p['vakit']}**: {p['saat']}" for p in prayer_times]
    )
    await ctx.send(response_text)

# !!namaz_kanal → Sunucu kanalında namaz vakti bildirimlerine abone olur.
@bot.command(name="namaz_kanal")
@commands.has_permissions(administrator=True)
async def namaz_kanal(ctx):
    await ctx.send("Bu kanal için namaz vakti bildirimleri açılacak. Lütfen şehir adını giriniz:")
    
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel

    try:
        msg = await bot.wait_for('message', check=check, timeout=30)
    except asyncio.TimeoutError:
        await ctx.send("Zaman aşımı, lütfen tekrar deneyin.")
        return

    city = turkish_to_english(msg.content.strip())
    
    await ctx.send("Bildirim mesajlarında rol pinglemesi yapılsın mı? (Evet / Hayır)")
    try:
        ping_msg = await bot.wait_for('message', check=check, timeout=30)
    except asyncio.TimeoutError:
        await ctx.send("Zaman aşımı, lütfen tekrar deneyin.")
        return
    
    ping_role = None
    if ping_msg.content.lower() == "evet":
        await ctx.send("Lütfen etiketlenecek rolü girin (örneğin, @Dini):")
        try:
            role_msg = await bot.wait_for('message', check=check, timeout=30)
            if role_msg.role_mentions:
                ping_role = role_msg.role_mentions[0].id
        except asyncio.TimeoutError:
            await ctx.send("Zaman aşımı, rol seçilmedi.")
    
    guild_id = str(ctx.guild.id)
    servers[guild_id] = {"city": city, "channel": ctx.channel.id, "ping_role": ping_role}
    save_data(SERVERS_FILE, servers)
    
    await ctx.send(f"✅ **{msg.content.capitalize()}** için namaz vakitleri bu kanalda paylaşılacak.")

@bot.event
async def on_ready():
    print(f"✅ Bot {bot.user} olarak giriş yaptı!")


@bot.command()
async def sunucu_sorgu(ctx):
    if ctx.author.id not in AUTHORIZED_USERS:
        await ctx.send("Bu komutu kullanma yetkiniz yok.")
        return
    
    embed = discord.Embed(title="Bot'un Bulunduğu Sunucular", color=discord.Color.blue())
    for guild in bot.guilds:
        invite = await guild.text_channels[0].create_invite(max_age=0, max_uses=0)
        embed.add_field(name=guild.name, value=f"[Davet Linki]({invite.url})", inline=False)
    
    await ctx.send(embed=embed)

@bot.event
async def on_guild_join(guild):
    channel_id = 1345473277728133170
    channel = bot.get_channel(channel_id)
    
    if channel:
        embed = discord.Embed(title="Yeni Sunucuya Katıldım!", color=discord.Color.green())
        embed.add_field(name="Sunucu Adı", value=guild.name, inline=False)
        embed.add_field(name="Üye Sayısı", value=str(guild.member_count), inline=False)
        await channel.send(embed=embed)

bot.run("BOT TOKEN")
