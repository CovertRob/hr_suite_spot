const isProd = window.location.hostname === 'hrsuitespot.com';
const stripeKey = isProd
  ? 'pk_live_51R6J2zH8d4CYhArR056iPK0SSDoUfKd2a02RHmvWFBrGqyEGnpoLU99gC3HwA7uEGTEfchlPlOi867MD3GsFrUgQ00088LW1OY'
  : "pk_test_51R6J2zH8d4CYhArRbvokzS9EDTy87RR629fc4v5mJ0N087sCERV9tGrpI4w3n9WjNUEf4zFo9tIh0bjR8CyEqC3w00hj3krsQC";

const stripe = Stripe(stripeKey);

initialize();

function getQueryParams() {
  const params = new URLSearchParams(window.location.search);
  return {
    booking_name: params.get("booking_name"),
    booking_email: params.get("booking_email"),
    checkout_type: params.get("checkout_type"),
    checkout_amount: params.get("checkout_amount"),
    selected_datetime_utc: params.get("selected_datetime_utc"),
  };
}

async function initialize() {
  const fetchClientSecret = async () => {
    const queryParams = getQueryParams();

    // Build query string to match what your Flask route expects
    const url = new URL("/create-checkout-session", window.location.origin);
    url.search = new URLSearchParams(queryParams).toString();

    const response = await fetch(url.toString(), {
      method: "POST"
    });

    const { clientSecret } = await response.json();
    return clientSecret;
  };

  const checkout = await stripe.initEmbeddedCheckout({
    fetchClientSecret,
  });

  checkout.mount('#checkout');
}

// checkout.js (loads once per checkout page)
document.addEventListener("DOMContentLoaded", () => {
  /* -------- 1. pull config from HTML -------- */
  const cfgEl     = document.getElementById("checkout-data");
  if (!cfgEl) return;                            // safety

  const slotId    = cfgEl.dataset.slotId;        // string → backend is int
  const token     = cfgEl.dataset.holdToken;
  const interval  = Number(cfgEl.dataset.heartbeat);   // e.g. 30000

  /* -------- 2. heartbeat every N ms -------- */
  function extend() {
    fetch("/api/extend_hold", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ slot_id: slotId, token })
    });
  }
  const hb = setInterval(extend, interval);

  /* -------- 3. release instantly on close/back -------- */
  function release() {
    navigator.sendBeacon(
      "/api/release_hold",
      JSON.stringify({ slot_id: slotId, token })
    );
  }
  window.addEventListener("pagehide", release);      // fires on back/close
});
