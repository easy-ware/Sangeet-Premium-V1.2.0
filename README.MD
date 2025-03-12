# Sangeet Premium 🎵 V1.2.0

<p align="center">
  <img src="promo/logo2.png" alt="Sangeet Premium Logo" width="600" height="400"/>
</p>

A modern, open-source music player with a stunning user interface, smart recommendations, and high-quality audio streaming - completely free forever.

## 📋 Table of Contents
- [Why Sangeet Premium?](#-why-sangeet-premium)
- [Features](#-features)
- [Requirements](#-requirements)
- [Installation](#-installation)
  - [Standard Installation](#standard-installation)
  - [Docker Installation](#docker-installation)
- [Configuration](#-configuration)
- [Usage](#-usage)
- [Troubleshooting](#-troubleshooting)
- [Contributing](#-contributing)
- [License](#-license)
- [Acknowledgments](#-acknowledgments)
- [Contact](#-contact)

## 🌟 Why Sangeet Premium?
In today's digital music landscape, listeners face several challenges:
- Major streaming platforms charge premium fees for high-quality audio
- Expensive subscription models with restrictive features
- Limited control over music organization and playback
- Closed ecosystems that lock users into specific platforms
- Algorithmic recommendations that often prioritize promoted content

Sangeet Premium solves these issues by providing:
- Completely free, high-quality audio streaming
- Beautiful, responsive user interface
- Advanced music recommendation system
- Full control over your music library
- No ads, no subscriptions, no limitations
- Ability to share songs and embed them in other platforms

## ✨ Features
- **Stunning UI/UX**: Modern, intuitive interface with smooth animations
- **Smart Recommendations**: AI-powered music suggestions based on your listening habits
- **High-Quality Audio**: Crystal clear audio streaming with no compromises
- **Library Management**: Organize your music collection effortlessly
- **Cross-Platform**: Available on Windows, macOS, and Linux
- **Offline Mode**: Download your favorite tracks for offline listening
- **Last.fm Integration**: Scrobble your listening history
- **Customizable Themes**: Personalize your player's appearance
- **Lyrics Support**: Real-time synchronized lyrics
- **Smart Login System**: Secure and easy authentication
- **Playlist System**: Create, manage, and share playlists with friends

## 📋 Requirements
- Python 3.12 or higher
- FFmpeg
- Cloudflared (for remote access)
- Docker (optional, for containerized deployment)

## 🚀 Installation

### Standard Installation

1. **Clone the repository**
```bash
git clone https://github.com/easy-ware/Sangeet-Premium-V1.2.0.git
cd Sangeet-Premium-V1.2.0
```

2. **Install dependencies**
```bash
pip install -r requirements/req.txt
```

3. **Install required system packages**

For Debian/Ubuntu-based systems:
```bash
# Install FFmpeg
sudo apt update
sudo apt install ffmpeg

# Install Cloudflared
wget "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb"
sudo dpkg -i cloudflared-linux-amd64.deb
```

For other Linux distributions, please refer to the official documentation for FFmpeg and Cloudflared installation.

4. **Configure environment variables**
Create a `/config/.env` file in the root directory with the following configuration:
```env
# ---------------------------
# SMTP Credentials
# ---------------------------
SMTP_USER=your_email@gmail.com         # Email address for SMTP authentication
SMTP_PASSWORD="your_app_password"      # SMTP password or app-specific password
SMTP_HOST=smtp.gmail.com               # SMTP server hostname
SMTP_PORT=587                          # SMTP server port number

# ---------------------------
# Local Music Configuration
# ---------------------------
LOCAL_SONGS_PATHS="/path/to/music"     # Primary path for local music files
music_path="/path/to/sangeet/music"    # Sangeet music directory path

# ---------------------------
# Server Configuration
# ---------------------------
SANGEET_BACKEND=http://localhost       # Backend server URL
PORT=80                                # Server port number

# ---------------------------
# Database Configuration
# ---------------------------
DB_PATH="database_files"               # Path to database files

# ---------------------------
# Authentication For Admin
# ---------------------------
admin_pass="your_secure_password"      # Admin password for authentication
```

5. **Run the application**
```bash
python start_server.py
# or
python3 start_server.py
```

If you encounter any issues, try running the server directly:
```bash
python sangeet_server.py
# or
python3 sangeet_server.py
```

### Docker Installation

1. **Clone the repository**
```bash
git clone https://github.com/easy-ware/Sangeet-Premium-V1.2.0.git
cd Sangeet-Premium
```

2. **Build the Docker image**
```bash
docker build -t sangeet-premiumv1.2.0:local .
```

3. **Configure docker-compose.yaml**
Create or modify the `docker-compose.yaml` file:
```yaml
services:
  sangeet:
    image: sangeet-premiumv1.2.0:local # Change to "tetsingimagesnet/sangeet-premiumv1.2.0:dev" if using pre-built image
    restart: always
    ports:
      - "0.0.0.0:80:80"
    volumes:
      - /path/to/your/config:/sangeet/config
      - /path/to/your/database_files:/sangeet/database_files
      - /path/to/your/music:/sangeet/music
```

4. **Run with Docker Compose**
```bash
docker compose up
```

To run in detached mode:
```bash
docker compose up -d
```

Alternatively, you can use the pre-built image:
```bash
docker pull tetsingimagesnet/sangeet-premiumv1.2.0:dev
docker compose up -d
```

## ⚙️ Configuration

### Environment Variables
For detailed explanation of each environment variable, refer to the comments in the `.env` file template above.

### Directory Structure
- `/config` - Contains configuration files including `.env`
- `/database_files` - Stores SQLite database files
- `/music` - Directory for storing music files
- `/requirements` - Contains dependency files

## 🎮 Usage
Once the server is running, access the Sangeet Premium interface by navigating to:
- Local access: `http://localhost:80` (or the port you configured)
- Remote access: Use the Cloudflared tunnel URL generated during startup

> **Note:** For accessing Sangeet from other devices on your network, you must use the Cloudflared tunnel URL (ending with `.trycloudflare.com`). Direct access via local IP addresses (like 192.168.0.1) may not work properly.
# Visit /settings to manage your server enter admin pass
## 🔧 Troubleshooting

### Common Issues
1. **Server won't start**
   - Ensure Python 3.12+ is installed
   - Verify all dependencies are installed correctly
   - Check if the required ports are available

2. **Can't access from other devices**
   - Make sure to use the Cloudflared tunnel URL
   - Verify network settings and firewall configurations

3. **Missing audio features**
   - Confirm FFmpeg is properly installed and accessible in PATH

### Reporting Issues
If you encounter any bugs or have feature requests, please report them on our [GitHub Issues page](https://github.com/easy-ware/Sangeet-Premium-V1.2.0.git) with the following information:
- Detailed description of the issue
- Steps to reproduce
- Expected vs. actual behavior
- System information (OS, Python version, etc.)
- Screenshots or logs (if applicable)

## 🤝 Contributing
We welcome contributions from the community! Here's how you can contribute:

1. **Fork the repository**
2. **Create a new branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. **Make your changes**
4. **Test thoroughly**
5. **Commit your changes**
   ```bash
   git commit -m "Add feature: your feature description"
   ```
6. **Push to your fork**
   ```bash
   git push origin feature/your-feature-name
   ```
7. **Create a Pull Request**

Please ensure your code follows our coding standards and includes appropriate documentation.

## 📜 License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments
- All the open-source libraries and tools used in this project
- The community of contributors and users

## 📧 Contact
- GitHub: [Easy Ware](https://github.com/easy-ware)
- Issue Tracker: [GitHub Issues](https://github.com/easy-ware/Sangeet-Premium/issues)

---
<p align="center">
  Made with ❤️ by the Sangeet Premium Team
</p>
