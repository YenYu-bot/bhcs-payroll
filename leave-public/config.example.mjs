// File for the separate leave project only. Never use the existing payroll project.
export const config = {
  apiKey: 'REPLACE_WITH_LEAVE_WEB_API_KEY',
  authDomain: 'REPLACE_WITH_LEAVE_AUTH_DOMAIN',
  projectId: 'REPLACE_WITH_LEAVE_PROJECT_ID',
  appId: 'REPLACE_WITH_LEAVE_WEB_APP_ID'
};
// Both values must be HTTPS in production and have distinct origins.
export const staffOrigin = 'https://REPLACE-WITH-LEAVE-SITE.web.app';
export const managerOrigin = 'https://yenyu-bot.github.io';

// Public web settings from the existing classroom project, not service account credentials.
export const journalConfig = {
  apiKey: 'REPLACE_WITH_JOURNAL_WEB_API_KEY',
  authDomain: 'bhcs-system.firebaseapp.com',
  projectId: 'bhcs-system',
  appId: 'REPLACE_WITH_JOURNAL_WEB_APP_ID'
};
export const journalExchangeUrl = 'https://asia-east1-bhcs-leave.cloudfunctions.net/exchangeJournalLogin';
