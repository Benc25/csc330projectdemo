FLASK_APP=main.py
FLASK_DEBUG=1
SQLITE_DB=recipe.db
FLASK_RUN_HOST=0.0.0.0
FLASK_RUN_PORT=8080

# Email Configuration (Gmail SMTP)
# For Gmail, use an App Password (not your regular password)
# 1. Enable 2-Step Verification in your Google Account
# 2. Generate an App Password at https://myaccount.google.com/apppasswords
# You can also use any other SMTP server by updating these settings
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-password-16-characters
MAIL_DEFAULT_SENDER=your-email@gmail.com

# Secret key for Flask sessions
SECRET_KEY=open-kitchen-demo-change-in-production
