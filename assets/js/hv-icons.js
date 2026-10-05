/* Platform marks shared by the campaign report and the creator analysis page —
   the same drawn icons the catalogue cards use (copied from catalogue.js so
   those pages do not load the whole catalogue script). */
(function () {
  var TT = '<path d="M14.2 3v11.6a3.6 3.6 0 1 1-3.6-3.6"/><path d="M14.2 3.2c.45 2.7 2.05 4.3 4.75 4.6"/>';
  var ICONS = {
    Instagram: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="5"/><circle cx="12" cy="12" r="4.1"/><circle cx="17.3" cy="6.7" r="1.15" fill="currentColor" stroke="none"/></svg>',
    TikTok: '<svg viewBox="0 0 24 24" fill="none" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
      '<g stroke="#25f4ee" transform="translate(-1,-.85)">' + TT + '</g>' +
      '<g stroke="#fe2c55" transform="translate(1,.85)">' + TT + '</g>' +
      '<g stroke="currentColor">' + TT + '</g></svg>'
  };
  ICONS.Snapchat = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3.2c2.4 0 4 1.7 4 4.1 0 1 .1 1.7.3 2.1.3.4.9.4 1.4.3.4-.1.8.2.8.6 0 .5-.6.8-1.2 1-.3.1-.4.3-.3.6.4 1.2 1.6 2.4 3 2.7.3.1.4.4.2.6-.5.6-1.6.9-2.5 1-.2.5-.3 1-.9 1-.5 0-1-.3-1.8-.3-1.1 0-1.6 1.1-3 1.1s-1.9-1.1-3-1.1c-.8 0-1.3.3-1.8.3-.6 0-.7-.5-.9-1-.9-.1-2-.4-2.5-1-.2-.2-.1-.5.2-.6 1.4-.3 2.6-1.5 3-2.7.1-.3 0-.5-.3-.6-.6-.2-1.2-.5-1.2-1 0-.4.4-.7.8-.6.5.1 1.1.1 1.4-.3.2-.4.3-1.1.3-2.1 0-2.4 1.6-4.1 4-4.1z"/></svg>';
  ICONS.YouTube = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" aria-hidden="true"><rect x="2.5" y="5.5" width="19" height="13" rx="4"/><path d="M10.2 9.3l5 2.7-5 2.7z" fill="currentColor" stroke="none"/></svg>';
  ICONS.X = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><path d="M4.5 4.5l15 15M19.5 4.5l-15 15"/></svg>';
  ICONS.Facebook = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15.2 4.2h-2.1a3.4 3.4 0 0 0-3.4 3.4V10H7.9v3h1.8v7"/><path d="M9.7 13h4.1"/></svg>';
  var ICON_LINK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10 13.5a3.5 3.5 0 0 0 5 0l2.5-2.5a3.5 3.5 0 0 0-5-5L11 7.5"/><path d="M14 10.5a3.5 3.5 0 0 0-5 0L6.5 13a3.5 3.5 0 0 0 5 5l1.5-1.5"/></svg>';
  window.HV_ICONS = { icons: ICONS, link: ICON_LINK };
})();
