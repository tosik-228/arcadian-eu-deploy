// Public contacts shared by the localized homepage and PDF rate pages.
export const siteContacts = {
  email: 'info@arcadian-eu.com',
  main: {number: '+32466495409', display: '+32 466 495 409', whatsapp: 'https://wa.me/32466495409'},
  poland: {number: '+48734472003', display: '+48 734 472 003', whatsapp: 'https://wa.me/48734472003'},
};

const labels = {
  en: {email: 'Projects, subcontracting and careers', main: 'Main contact', poland: 'Corporate number · Poland', hours: 'Mon–Fri, 08:00–18:00 CET', whatsapp: 'Open WhatsApp chat', sent: 'Your request has reached the ARCADIAN office. Our team will contact you shortly from'},
  pl: {email: 'Projekty, podwykonawstwo i praca', main: 'Główny kontakt', poland: 'Numer firmowy · Polska', hours: 'Pn–Pt, 08:00–18:00 CET', whatsapp: 'Otwórz czat WhatsApp', sent: 'Wiadomość dotarła do biura ARCADIAN. Nasz zespół skontaktuje się wkrótce z numeru'},
  nl: {email: 'Projecten, onderaanneming en vacatures', main: 'Hoofdcontact', poland: 'Bedrijfsnummer · Polen', hours: 'Ma–Vr, 08:00–18:00 CET', whatsapp: 'Open WhatsApp-chat', sent: 'Je bericht is aangekomen bij ARCADIAN. Ons team neemt binnenkort contact op via'},
};

const whatsapp = (contact, label) => `<a class="contact-channel" href="${contact.whatsapp}" target="_blank" rel="noopener noreferrer" aria-label="${label}: ${contact.display}" title="WhatsApp · ${contact.display}"><i class="bi bi-whatsapp" aria-hidden="true"></i></a>`;
const phone = (contact) => `<a href="tel:${contact.number}">${contact.display.replaceAll(' ', '&nbsp;')}</a>`;

export function contactFacts(locale) {
  const t = labels[locale];
  return `<div class="c-fact">
            <span class="ic"><i class="bi bi-envelope" aria-hidden="true"></i></span>
            <div><div class="contact-value"><b><a href="mailto:${siteContacts.email}">${siteContacts.email}</a></b>${whatsapp(siteContacts.main, t.whatsapp)}</div>
              <small>${t.email}</small></div>
          </div>
          <div class="c-fact">
            <span class="ic"><i class="bi bi-telephone" aria-hidden="true"></i></span>
            <div><b>${phone(siteContacts.main)}</b>
              <small>${t.main} · ${t.hours}</small></div>
          </div>
          <div class="c-fact">
            <span class="ic"><i class="bi bi-building" aria-hidden="true"></i></span>
            <div><div class="contact-value"><b>${phone(siteContacts.poland)}</b>${whatsapp(siteContacts.poland, t.whatsapp)}</div>
              <small>${t.poland}</small></div>
          </div>`;
}

export function contactStrip(locale) {
  const t = labels[locale];
  return `<div class="content-contacts">
      <div class="content-contact"><span>${t.main}</span><div class="contact-value">${phone(siteContacts.main)}</div></div>
      <div class="content-contact"><span>Email · WhatsApp</span><div class="contact-value"><a href="mailto:${siteContacts.email}">${siteContacts.email}</a>${whatsapp(siteContacts.main, t.whatsapp)}</div></div>
      <div class="content-contact"><span>${t.poland}</span><div class="contact-value">${phone(siteContacts.poland)}${whatsapp(siteContacts.poland, t.whatsapp)}</div></div>
    </div>`;
}

export function contactConfirmation(locale) {
  return `${labels[locale].sent} ${siteContacts.main.display}.`;
}
