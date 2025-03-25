// This is your test secret API key.
const stripe = Stripe("pk_test_51R6J2zH8d4CYhArRbvokzS9EDTy87RR629fc4v5mJ0N087sCERV9tGrpI4w3n9WjNUEf4zFo9tIh0bjR8CyEqC3w00hj3krsQC");

initialize();

// Create a Checkout Session
async function initialize() {
  const fetchClientSecret = async () => {
    const response = await fetch("/create-checkout-session", {
      method: "POST",
    });
    const { clientSecret } = await response.json();
    return clientSecret;
  };

  const checkout = await stripe.initEmbeddedCheckout({
    fetchClientSecret,
  });

  // Mount Checkout
  checkout.mount('#checkout');
}