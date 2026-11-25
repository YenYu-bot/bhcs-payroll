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
