# MediaCMS Bulk Title & Description Editor

A lightweight Python GUI for bulk editing **titles** and **descriptions** of videos on a self-hosted MediaCMS instance.

![Screenshot](https://github.com/jonrick/MediaCMSBulkEditor/blob/main/screenshot.png "screenshot")

---

**A simple GUI tool to bulk-edit MediaCMS basic video metadata.**

---

## ✨ Features

* Connects to your self-hosted MediaCMS via its API
* Fetches and lists uploaded media
* Bulk edit titles and descriptions quickly and safely
* Simple configuration using `config.ini` (example included)

---

## ⚙️ Setup

1. Clone the repository:

   ```bash
   git clone https://github.com/jonrick/MediaCMSBulkEditor.git
   cd MediaCMSBulkEditor
   ```

2. Edit config.ini with your MediaCMS credentials:

   ```bash
   nano config.ini
   ```

   Example `config.ini` contents:

   ```ini
   [prefs]
   app_title = MediaCMS Video Details Editor

   [auth]
   api_url = https://your-mediacms-instance/api/v1/media/
   username = your_username
   password = your_password
   ```

   * **API_URL**: the base API URL for your MediaCMS instance (include the trailing slash). Example: `https://example.com/api/v1/media/`
   * **USERNAME / PASSWORD**: account credentials with permission to edit media metadata.

---

## 📦 Requirements

* **Python 3.9+**
* Dependencies listed in `requirements.txt`:

  * `requests`
  * `PySide6`

Install dependencies with:

```
pip install -r requirements.txt
```

---

## ▶️ Usage

Run the editor with:

```bash
python main.py
```

A window will open showing your media list. Select one or more videos and update their titles and descriptions in bulk. If you make a mistake you can revert that specific video's details. When finished making your changes, click "push changes" to hit the API and push the changes live to your site.

---

## 🛠 Troubleshooting

* If you get authentication errors, double-check `API_URL` (include trailing slash) and credentials.
* If the media list is empty but you have media in MediaCMS, check that the API URL is correct and that the account has API access permissions.
* For GUI issues on Linux, ensure your system Qt packages are compatible when installing `PySide6`.

---

## 🤝 Contributing

Pull requests are welcome. If you open a PR, please:

* Describe the change and why it helps
* Keep changes small and well-scoped
* Follow existing code style

If you want to contribute large features, open an issue first to discuss.

---

## 📜 License

See the `LICENSE` file in this repository for license terms. This project is intended for personal / non-commercial use. Derivative works should remain open and reference this project.


---

