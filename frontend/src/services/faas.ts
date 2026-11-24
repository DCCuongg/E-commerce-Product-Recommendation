import { DEMO_MODE } from './auth';

export type InteractionAction = 'view' | 'click' | 'add_to_cart' | 'checkout' | 'purchase' | 'rating';

const FAAS_ENDPOINT = (import.meta.env.VITE_FAAS_URL || '/api/LogInteractionFunction').replace(/\/$/, '');

export async function logInteraction(params: {
  userId?: string;
  productId: string;
  action: InteractionAction;
  value?: number | null;
}): Promise<void> {
  if (!params.productId) return;
  if (DEMO_MODE) {
    console.debug('[DEMO FaaS]', params);
    return;
  }

  try {
    await fetch(FAAS_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: params.userId || 'anonymous',
        product_id: params.productId,
        action: params.action,
        value: params.value ?? null,
      }),
      keepalive: true,
    });
  } catch (err) {
    console.warn('[FaaS] Interaction log skipped:', err);
  }
}