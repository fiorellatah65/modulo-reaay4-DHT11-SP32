#!/bin/bash

# 🚀 Script de Setup Rápido para ESP32 Netlify
# Ejecutar con: bash setup.sh

echo "🚀 ESP32 Control - Setup Automatizado"
echo "======================================"
echo ""

# Colores
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Verificar que estamos en la carpeta correcta
if [ ! -f "index.html" ]; then
    echo -e "${RED}❌ Error: No encuentro index.html${NC}"
    echo "Por favor ejecuta este script en la carpeta del proyecto"
    exit 1
fi

echo -e "${GREEN}✅ Archivos encontrados${NC}"
echo ""

# Verificar estructura
echo "📁 Verificando estructura de carpetas..."
if [ ! -d "netlify/functions" ]; then
    echo -e "${YELLOW}⚠️  Creando carpeta netlify/functions...${NC}"
    mkdir -p netlify/functions
fi

if [ ! -f "netlify/functions/telegram-bot.js" ]; then
    echo -e "${RED}❌ Falta telegram-bot.js en netlify/functions/${NC}"
    echo "Por favor copia el archivo antes de continuar"
    exit 1
fi

echo -e "${GREEN}✅ Estructura correcta${NC}"
echo ""

# Verificar Node.js
echo "🔍 Verificando Node.js..."
if ! command -v node &> /dev/null; then
    echo -e "${RED}❌ Node.js no está instalado${NC}"
    echo "Instala Node.js desde: https://nodejs.org/"
    exit 1
fi

NODE_VERSION=$(node -v)
echo -e "${GREEN}✅ Node.js $NODE_VERSION${NC}"
echo ""

# Verificar package.json
if [ ! -f "package.json" ]; then
    echo -e "${YELLOW}⚠️  Falta package.json, creando...${NC}"
    cat > package.json << 'EOF'
{
  "name": "esp32-telegram-control",
  "version": "1.0.0",
  "description": "ESP32 Control System",
  "dependencies": {
    "mqtt": "^4.3.7",
    "node-fetch": "^2.7.0",
    "form-data": "^4.0.0",
    "google-tts-api": "^2.0.2"
  }
}
EOF
fi

# Instalar dependencias
echo "📦 Instalando dependencias..."
npm install
echo -e "${GREEN}✅ Dependencias instaladas${NC}"
echo ""

# Verificar Git
echo "🔍 Verificando Git..."
if ! command -v git &> /dev/null; then
    echo -e "${RED}❌ Git no está instalado${NC}"
    echo "Instala Git desde: https://git-scm.com/"
    exit 1
fi

if [ ! -d ".git" ]; then
    echo -e "${YELLOW}⚠️  Inicializando repositorio Git...${NC}"
    git init
    
    # Crear .gitignore
    cat > .gitignore << 'EOF'
node_modules/
.env
.netlify/
*.log
.DS_Store
EOF
    
    git add .
    git commit -m "Initial commit - ESP32 Control System"
    echo -e "${GREEN}✅ Git inicializado${NC}"
else
    echo -e "${GREEN}✅ Git ya inicializado${NC}"
fi
echo ""

# Información de despliegue
echo "======================================"
echo -e "${GREEN}✅ SETUP COMPLETADO${NC}"
echo "======================================"
echo ""
echo "📋 PRÓXIMOS PASOS:"
echo ""
echo "1️⃣  SUBIR A GITHUB:"
echo "   ${YELLOW}# Crea un repo en github.com/new${NC}"
echo "   git remote add origin https://github.com/TU_USUARIO/TU_REPO.git"
echo "   git branch -M main"
echo "   git push -u origin main"
echo ""
echo "2️⃣  DEPLOY EN NETLIFY:"
echo "   ${YELLOW}# Ve a netlify.com${NC}"
echo "   - Add new site → Import from Git"
echo "   - Conecta GitHub → Selecciona tu repo"
echo "   - Deploy!"
echo ""
echo "3️⃣  CONFIGURAR VARIABLES:"
echo "   ${YELLOW}# En Netlify: Site settings → Environment variables${NC}"
echo "   - Name: TELEGRAM_TOKEN"
echo "   - Value: 8491255978:AAFfDy6smKSAhkcGjtX8HxHh6cXe9RB4Y44"
echo ""
echo "4️⃣  CONFIGURAR WEBHOOK:"
echo "   ${YELLOW}# Reemplaza TU_URL con tu URL de Netlify${NC}"
echo '   curl -X POST "https://api.telegram.org/bot8491255978:AAFfDy6smKSAhkcGjtX8HxHh6cXe9RB4Y44/setWebhook?url=https://relay4-mht11-bot.netlify.app/.netlify/functions/telegram-bot"'
echo ""
echo "======================================"
echo -e "${GREEN}🎉 ¡Todo listo para deploy!${NC}"
echo "======================================"