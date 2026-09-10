import os
import json
import requests
from dotenv import load_dotenv

# Last inn variabler fra lokal .env-fil på Pi-en
load_dotenv()

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")
USER_AGENT = os.getenv("MET_USER_AGENT", "NyhetsOvervaking/1.0 (desken@lokalavis.no)")

HEADERS = {"User-Agent": USER_AGENT}
URL = "https://api.met.no/weatherapi/metalerts/2.0/current.json"
SEEN_FILE = os.path.join(os.path.dirname(__file__), "seen_alerts.json")

# Kun Oransje og Rød sendes til desken (filtrerer bort gult)
ALLOWED_COLORS = ["Yellow", "Orange", "Red"]

# Fargekoder for Slack (sidefelt)
COLOR_MAP = {
    "Red": "#E02424",     # Ekstremt farevarsel
    "Orange": "#FF8A00",  # Svært alvorlig farevarsel
}

EMOJI_MAP = {
    "Red": "🔴",
    "Orange": "🟠",
}

# Oversettelsestabeller for engelske nøkler fra MET API
COLOR_NO = {
    "Yellow": "GULT",
    "Orange": "ORANSJE",
    "Red": "RØDT"
}

SEVERITY_NO = {
    "Yellow": "Moderat fare (Gult)",
    "Orange": "Svært alvorlig fare (Oransje)",
    "Red": "Ekstrem fare (Rødt)"
}

EVENT_NO = {
    "gale": "Kuling / Sterk vind",
    "wind": "Kraftige vindkast",
    "rain": "Kraftig regn",
    "heavy-rain": "Pøsregn / Skybrudd",
    "snow": "Snøfokk / Snøfall",
    "ice": "Is / Glatte veier",
    "flood": "Flom",
    "landslide": "Jordskredfare",
    "forest-fire": "Skogbrannfare",
    "polar-low": "Polart lavtrykk"
}

def load_seen():
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except json.JSONDecodeError:
            return set()
    return set()

def save_seen(seen_ids):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen_ids), f, indent=2)

def send_slack_notification(props):
    if not SLACK_WEBHOOK_URL:
        raise ValueError("SLACK_WEBHOOK_URL mangler i .env-filen!")

    color_raw = props.get("riskMatrixColor", "Orange")
    color_name = COLOR_NO.get(color_raw, color_raw.upper())
    slack_color = COLOR_MAP.get(color_raw, "#FF8A00")
    emoji = EMOJI_MAP.get(color_raw, "⚠️")

    # Oversett hendelsestype hvis den leveres på engelsk
    raw_event = str(props.get("event", "Værhendelse")).lower()
    event = EVENT_NO.get(raw_event, props.get("event", "Værhendelse").capitalize())

    area = props.get("area", "Ukjent område")
    description = props.get("description", "Ingen beskrivelse oppgitt.")
    instruction = props.get("instruction", "Ingen spesifikke råd oppgitt.")
    awareness = SEVERITY_NO.get(color_raw, "Alvorlig fare")

    payload = {
        "attachments": [
            {
                "color": slack_color,
                "blocks": [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": f"{emoji} {color_name} FAREVARSEL: {event}",
                            "emoji": True
                        }
                    },
                    {
                        "type": "section",
                        "fields": [
                            {"type": "mrkdwn", "text": f"*Område:*\n{area}"},
                            {"type": "mrkdwn", "text": f"*Alvorlighetsgrad:*\n{awareness}"}
                        ]
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*Beskrivelse:*\n{description}"
                        }
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*Anbefalt tiltak:*\n_{instruction}_"
                        }
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "mrkdwn",
                                "text": "🌤️ *Kilde:* Meteorologisk institutt (MET)"
                            }
                        ]
                    }
                ]
            }
        ]
    }

    response = requests.post(SLACK_WEBHOOK_URL, json=payload, timeout=10)
    response.raise_for_status()

def check_metalerts():
    try:
        response = requests.get(URL, headers=HEADERS, timeout=10)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print(f"Nettverks- eller parsing-feil fra MET: {e}")
        return

    seen_ids = load_seen()
    new_seen_ids = set(seen_ids)

    for feature in data.get("features", []):
        props = feature.get("properties", {})
        alert_id = props.get("id")
        color_name = props.get("riskMatrixColor")

        # Filtrer bort alt som ikke er Oransje eller Rødt
        if color_name not in ALLOWED_COLORS:
            continue

        if alert_id and alert_id not in seen_ids:
            try:
                send_slack_notification(props)
                print(f"🚨 Farevarsel sendt til Slack: [{color_name}] {props.get('event')} ({props.get('area')})")
                new_seen_ids.add(alert_id)
            except Exception as e:
                print(f"Feil ved sending av alert {alert_id} til Slack: {e}")

    save_seen(new_seen_ids)

if __name__ == "__main__":
    check_metalerts()
