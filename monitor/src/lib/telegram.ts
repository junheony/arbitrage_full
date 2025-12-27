import axios from 'axios';
import type { SpreadData, Alert } from './types';

const TELEGRAM_API = 'https://api.telegram.org/bot';

// Active alerts tracking (in-memory for serverless)
const activeAlerts = new Map<string, Alert>();

export async function sendTelegramMessage(
  botToken: string,
  chatId: string,
  message: string,
  parseMode: 'HTML' | 'Markdown' = 'HTML'
): Promise<boolean> {
  try {
    await axios.post(`${TELEGRAM_API}${botToken}/sendMessage`, {
      chat_id: chatId,
      text: message,
      parse_mode: parseMode,
    });
    return true;
  } catch (error) {
    console.error('Telegram send error:', error);
    return false;
  }
}

// Format spread alert message
export function formatSpreadAlert(spread: SpreadData): string {
  const emoji = spread.spreadPct > 0 ? '🔴' : '🟢';
  const direction = spread.spreadPct > 0 ? 'LONG GAP' : 'SHORT GAP';
  const leverageStr = spread.leverage ? ` ${spread.leverage}x` : '';

  const time = new Date(spread.timestamp).toLocaleTimeString('ko-KR', {
    timeZone: 'Asia/Seoul',
    hour: '2-digit',
    minute: '2-digit',
  });

  switch (spread.type) {
    case 'futures_gap':
      return `${emoji} <b>${spread.symbol}</b> (${spread.spreadPct > 0 ? '+' : ''}${spread.spreadPct.toFixed(3)}%)${leverageStr}
• ${direction}
• 선물: $${spread.sellPrice.toFixed(4)}
• 인덱스: $${spread.buyPrice.toFixed(4)}
• 시간: ${time}`;

    case 'cex_dex':
      return `🚨 <b>CEX-DEX ${spread.symbol}</b> (${spread.spreadPct.toFixed(2)}%)
• CEX: $${spread.sellPrice.toFixed(4)} (${spread.sellExchange})
• DEX: $${spread.buyPrice.toFixed(4)} (${spread.buyExchange})
• 시간: ${time}`;

    case 'kimchi':
      return `🇰🇷 <b>김프 ${spread.symbol}</b> (${spread.spreadPct > 0 ? '+' : ''}${spread.spreadPct.toFixed(2)}%)
• 국내: ₩${spread.sellPrice.toLocaleString()}
• 해외: $${spread.buyPrice.toFixed(2)}
• 시간: ${time}`;

    case 'funding':
      return `💰 <b>펀딩비 ${spread.symbol}</b> (${(spread.spreadPct * 100).toFixed(4)}%)
• 연율: ${(spread.spreadPct * 100 * 3 * 365).toFixed(1)}%
• 시간: ${time}`;

    default:
      return `📊 ${spread.symbol}: ${spread.spreadPct.toFixed(3)}%`;
  }
}

// Format close alert message
export function formatCloseAlert(spread: SpreadData): string {
  const time = new Date(spread.timestamp).toLocaleTimeString('ko-KR', {
    timeZone: 'Asia/Seoul',
    hour: '2-digit',
    minute: '2-digit',
  });

  return `⬜ <b>${spread.symbol} Closed</b> • 시간: ${time}`;
}

// Generate unique alert ID
function getAlertId(spread: SpreadData): string {
  return `${spread.type}_${spread.symbol}`;
}

// Process spread and send alert if needed
export async function processSpreadAlert(
  spread: SpreadData,
  threshold: number,
  botToken: string,
  chatId: string
): Promise<{ action: 'opened' | 'closed' | 'none'; alert?: Alert }> {
  const alertId = getAlertId(spread);
  const existingAlert = activeAlerts.get(alertId);
  const isAboveThreshold = Math.abs(spread.spreadPct) >= threshold;

  // New alert
  if (isAboveThreshold && !existingAlert) {
    const alert: Alert = {
      id: alertId,
      spread,
      sentAt: Date.now(),
      status: 'open',
    };
    activeAlerts.set(alertId, alert);

    const message = formatSpreadAlert(spread);
    await sendTelegramMessage(botToken, chatId, message);

    return { action: 'opened', alert };
  }

  // Close existing alert
  if (!isAboveThreshold && existingAlert && existingAlert.status === 'open') {
    existingAlert.status = 'closed';
    existingAlert.closedAt = Date.now();

    const message = formatCloseAlert(spread);
    await sendTelegramMessage(botToken, chatId, message);

    // Remove from active alerts after some time
    setTimeout(() => activeAlerts.delete(alertId), 60000);

    return { action: 'closed', alert: existingAlert };
  }

  return { action: 'none' };
}

// Get all active alerts
export function getActiveAlerts(): Alert[] {
  return Array.from(activeAlerts.values()).filter(a => a.status === 'open');
}

// Clear all alerts (for testing)
export function clearAlerts(): void {
  activeAlerts.clear();
}
