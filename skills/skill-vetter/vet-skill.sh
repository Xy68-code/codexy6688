#!/bin/bash
# Skill Vetter - Pre-install security check
# Usage: ./vet-skill.sh <skill-name>

SKILL_NAME=$1

if [ -z "$SKILL_NAME" ]; then
    echo "Usage: ./vet-skill.sh <skill-name>"
    exit 1
fi

echo "═══════════════════════════════════════"
echo "SKILL VETTING REPORT"
echo "═══════════════════════════════════════"
echo "Skill: $SKILL_NAME"
echo "Source: ClawdHub"
echo "───────────────────────────────────────"

# Search for skill info
echo "Searching ClawdHub..."
clawhub search "$SKILL_NAME" 2>&1 | head -10

echo ""
echo "⚠️  IMPORTANT SECURITY CHECKLIST:"
echo "───────────────────────────────────────"
echo "Before installing, you MUST:"
echo ""
echo "1. Review SKILL.md for the skill"
echo "2. Check for RED FLAGS:"
echo "   • curl/wget to unknown URLs"
echo "   • Sends data to external servers"
echo "   • Requests credentials/tokens/API keys"
echo "   • Reads ~/.ssh, ~/.aws, ~/.config"
echo "   • Accesses MEMORY.md, USER.md, SOUL.md"
echo "   • Uses eval() or exec() with external input"
echo "   • Obfuscated or minified code"
echo ""
echo "3. Evaluate risk level:"
echo "   🟢 LOW - Notes, weather, formatting"
echo "   🟡 MEDIUM - File ops, browser, APIs"
echo "   🔴 HIGH - Credentials, trading, system"
echo "   ⛔ EXTREME - Security configs, root access"
echo ""
echo "═══════════════════════════════════════"
