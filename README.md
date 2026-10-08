# Discord Bot — Olobywater

A custom Discord bot built with `discord.py` (v2.4+) designed for free hosting environments (low RAM, stateless disk, frequent restarts). It manages member verification through user introductions, automated role permissions, temporary bans without a database, and automatic TikTok notifications for **@olobywater**.

---

## 🌟 Key Features

### 1. Presentation & Verification System
* **Automatic Role Assignment**: New members automatically receive the `Non-verified` role upon joining, restricting access to all server channels except `#presentation`.
* **Welcome & Instructions**: Posts welcome instructions in `#presentation` requiring a single message with a minimum of 50 characters (age, interests, reason for joining).
* **Mod Validation Panel**: Validated presentations are automatically forwarded to `#validation-modos` as a rich Embed with interactive action buttons (**Accept** / **Refuse**).
* **Dynamic Persistence**: Interactive UI components use `discord.ui.DynamicItem` with regex pattern custom IDs (`accepter:<user_id>`, `refuser:<user_id>:<msg_id>`), ensuring buttons and sanction dropdowns work seamlessly even after bot restarts without a database.
* **Auto Cleanup**: Once a presentation is submitted, the bot automatically removes its welcome message from `#presentation` to keep the channel clean.

### 2. Sanction & Temporary Ban Management (Database-less)
* **Interactive Sanction Menu**: Clicking **Refuse** displays an ephemeral dropdown menu to moderators with options: Kick, Ban 1 day, Ban 7 days, Ban 30 days, or Permanent Ban.
* **Pre-Sanction Direct Message**: Sends an informative DM to the user *before* applying the kick/ban so they know why they were sanctionned.
* **Stateless Tempbans**: Temporary ban expiration dates are encoded directly into the ban reason string (`TEMPBAN|ISO8601_TIMESTAMP|Reason`). A background task regularly parses guild bans and lifts expired ones automatically.

### 3. TikTok Notifications (`@olobywater`)
* **Automated Scraper (`yt-dlp`)**: Periodically checks for new TikTok uploads directly via `yt-dlp` every 10 minutes without relying on third-party paid RSS services.
* **Multi-Video Catch-up & State Persistence**: Saves the last notified video ID in `dernier_tiktok.txt`. If the bot was offline, it detects all missed videos and posts them in chronological order.
* **Rich Native Previews**: Posts clean notification messages formatted with video title and raw URL to allow Discord to render full native video previews.

### 4. Console Management Scripts
* `post_tiktok.py`: Manually share a TikTok video link via the console.
* `delete_message.py`: Delete specific Discord messages by ID via the console.
* `role_nonverifie.py`: Manually add or remove the `Non-verified` role for any user by ID.

---

## ⚙️ Environment Variables

Create a `.env` file or set the following environment variables in your hosting provider (e.g., Railway):

| Variable | Description | Default / Optional |
|---|---|---|
| `TOKEN` | Discord Bot Token from Developer Portal | **Required** |
| `ID_PRESENTATION` | Channel ID for `#presentation` | **Required** |
| `ID_ROLE_MODO` | Role ID for Moderators | **Required** |
| `ID_VALIDATION` | Channel ID for `#validation-modos` | `0` (Auto-created on startup if 0) |
| `ID_ROLE_NONVERIFIE` | Role ID for `Non-verified` role | `0` (Auto-created on startup if 0) |
| `ID_SALON_TIKTOK` | Channel ID for TikTok notifications | Optional |
| `TIKTOK_USER_URL` | TikTok profile URL to track | `https://www.tiktok.com/@olobywater` |

---

## 🚀 Installation & Local Run

1. **Clone the repository**:
   ```bash
   git clone https://github.com/Naloulii/discord-bot-Olobywater.git
   cd discord-bot-Olobywater
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables**:
   Copy `.env.example` to `.env` and fill in your Discord credentials.

4. **Run the bot**:
   ```bash
   python main.py
   ```

---

## 🛠️ Console Helper Tools

```bash
# Post a TikTok video manually to the notification channel
python post_tiktok.py https://www.tiktok.com/@olobywater/video/123456789

# Delete a specific message by ID
python delete_message.py <message_id> [channel_id]

# Add or remove Non-verified role for a member
python role_nonverifie.py ajouter <user_id>
python role_nonverifie.py retirer <user_id>
```
