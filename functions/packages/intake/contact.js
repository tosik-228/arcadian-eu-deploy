const successMessage =
  "Your request has reached the ARCADIAN office. Anastasiya or a project manager will contact you shortly from +49 157 5624 0180.";

export async function main(event) {
  const method = event?.http?.method || "GET";
  if (method === "OPTIONS") {
    return response(204, "");
  }
  if (method !== "POST") {
    return response(405, "Method not allowed");
  }

  const endpoint = process.env.WERFVOLT_LEAD_ENDPOINT || "https://werfvolt.be/api/public/leads";
  const intakeKey = process.env.WERFVOLT_INTAKE_API_KEY || "";
  if (!intakeKey) {
    return response(503, "Contact form is not configured.");
  }

  const payload = normalize(event || {});
  const validation = validate(payload);
  if (validation) {
    return response(400, validation);
  }

  if (payload.website) {
    return response(200, { status: "received", message: successMessage });
  }

  const upstream = await fetch(endpoint, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Werfvolt-Intake-Key": intakeKey
    },
    body: JSON.stringify({
      type: payload.inquiryType || "contact",
      name: payload.name,
      email: payload.email,
      phone: payload.phone,
      company: "Arcadian landing",
      subject: payload.subject,
      message: payload.message,
      website: payload.website,
      startedAt: payload.startedAt
    })
  });

  if (!upstream.ok) {
    console.error(`Werfvolt intake failed with ${upstream.status}`);
    return response(502, "The message could not be sent. Please try again later.");
  }

  return response(200, { status: "received", message: successMessage });
}

function normalize(event) {
  return {
    inquiryType: clean(event.inquiryType || event.type || "contact"),
    name: clean(event.name),
    email: clean(event.email).toLowerCase(),
    phone: clean(event.phone),
    subject: clean(event.subject),
    message: clean(event.message),
    website: clean(event.website),
    startedAt: Number(event.startedAt || 0) || undefined
  };
}

function validate(payload) {
  if (!payload.name || !payload.email || !payload.subject || !payload.message) {
    return "Name, email, subject, and message are required.";
  }
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(payload.email)) {
    return "Please enter a valid email address.";
  }
  if (payload.name.length > 160 || payload.email.length > 180 || payload.subject.length > 160) {
    return "Please shorten the contact details and try again.";
  }
  if (payload.message.length > 4000) {
    return "Please shorten the message and try again.";
  }
  return "";
}

function clean(value) {
  return typeof value === "string" ? value.trim() : "";
}

function response(statusCode, body) {
  const isJson = typeof body === "object";
  return {
    statusCode,
    headers: {
      "Content-Type": isJson ? "application/json; charset=utf-8" : "text/plain; charset=utf-8",
      "Cache-Control": "no-store"
    },
    body
  };
}
