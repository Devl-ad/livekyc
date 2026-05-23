#!/bin/bash
# ────────────────────────────────────────────
#  lIVE VERIFICATION – Quick Setup Script
# ────────────────────────────────────────────
set -e

echo "📦 Installing dependencies..."
pip install -r requirements.txt --break-system-packages -q

echo "🗄️  Running migrations..."
python manage.py makemigrations accounts letters payments
python manage.py migrate

echo "👤 Creating superuser (admin)..."
python manage.py shell -c "
from apps.accounts.models import User
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@smartwriting.com', 'Admin1234!')
    print('  ✅ Superuser created: admin / Admin1234!')
else:
    print('  ℹ️  Superuser already exists.')
"

echo ""
echo "✅ Setup complete! Run the server:"
echo "   python manage.py runserver"
echo ""
echo "   Home:    http://127.0.0.1:8000/"
 