import api from '../config/api';

// ── Types ───────────────────────────────────────────────────────────

export interface SubscriptionPlan {
  id: string;
  name: string;
  plan_code: string;
  description: string;
  price_monthly_cents: number;
  price_yearly_cents: number;
  currency: string;
  is_recommended: boolean;
  is_custom_pricing: boolean;
  features_json: string[];
  sort_order: number;
}

export interface TenantSubscription {
  id: string;
  plan: SubscriptionPlan;
  status: 'active' | 'past_due' | 'canceled' | 'trialing' | 'incomplete' | 'incomplete_expired' | 'unpaid' | 'paused';
  billing_interval: 'month' | 'year';
  stripe_customer_id: string;
  current_period_start: string | null;
  current_period_end: string | null;
  cancel_at_period_end: boolean;
  canceled_at: string | null;
  trial_start: string | null;
  trial_end: string | null;
  created_at: string;
  updated_at: string;
}

export interface PaymentHistoryItem {
  id: string;
  amount_cents: number;
  currency: string;
  status: 'paid' | 'failed' | 'pending' | 'refunded';
  description: string;
  invoice_url: string;
  invoice_pdf_url: string;
  period_start: string | null;
  period_end: string | null;
  failure_reason: string;
  created_at: string;
}

export interface CheckoutSessionData {
  plan_id: string;
  interval: 'month' | 'year';
  success_url: string;
  cancel_url: string;
}

export interface PlanChangePreview {
  prorated_amount_cents: number;
  next_billing_date: string;
  new_plan: SubscriptionPlan;
}

// ── API service ─────────────────────────────────────────────────────

export const billingService = {
  // Public (no auth required)
  async getPlans(): Promise<SubscriptionPlan[]> {
    const res = await api.get('/billing/plans/');
    return res.data.results ?? res.data;
  },

  // Admin-only
  async getCurrentSubscription(): Promise<TenantSubscription | null> {
    try {
      const res = await api.get('/billing/subscription/');
      return res.data;
    } catch (err: any) {
      if (err?.response?.status === 404) return null;
      throw err;
    }
  },

  async getPaymentHistory(params?: { page?: number }): Promise<PaymentHistoryItem[]> {
    const res = await api.get('/billing/payments/', { params });
    return res.data.results ?? res.data;
  },

  async createCheckoutSession(data: CheckoutSessionData): Promise<{ checkout_url: string }> {
    const res = await api.post('/billing/checkout/', data);
    return res.data;
  },

  async createPortalSession(): Promise<{ portal_url: string }> {
    const res = await api.post('/billing/portal/');
    return res.data;
  },

  async previewPlanChange(data: { plan_id: string; interval: 'month' | 'year' }): Promise<PlanChangePreview> {
    const res = await api.post('/billing/preview-change/', data);
    return res.data;
  },
};
