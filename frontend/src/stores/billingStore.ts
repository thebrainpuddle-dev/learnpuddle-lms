import { create } from 'zustand';

import {
  billingService,
  type SubscriptionPlan,
  type TenantSubscription,
  type PaymentHistoryItem,
  type CheckoutSessionData,
  type PlanChangePreview,
} from '../services/billingService';

interface BillingState {
  plans: SubscriptionPlan[];
  subscription: TenantSubscription | null;
  payments: PaymentHistoryItem[];
  loading: boolean;
  error: string | null;

  fetchPlans: () => Promise<void>;
  fetchSubscription: () => Promise<void>;
  fetchPayments: (params?: { page?: number }) => Promise<void>;
  createCheckout: (data: CheckoutSessionData) => Promise<string>;
  openPortal: () => Promise<void>;
  previewChange: (planId: string, interval: 'month' | 'year') => Promise<PlanChangePreview>;
  reset: () => void;
}

const initialState = {
  plans: [],
  subscription: null,
  payments: [],
  loading: false,
  error: null,
};

export const useBillingStore = create<BillingState>((set) => ({
  ...initialState,

  fetchPlans: async () => {
    set({ loading: true, error: null });
    try {
      const plans = await billingService.getPlans();
      set({ plans, loading: false });
    } catch (err: any) {
      set({ error: err?.response?.data?.detail ?? err.message ?? 'Failed to fetch plans', loading: false });
    }
  },

  fetchSubscription: async () => {
    set({ loading: true, error: null });
    try {
      const subscription = await billingService.getCurrentSubscription();
      set({ subscription, loading: false });
    } catch (err: any) {
      set({ error: err?.response?.data?.detail ?? err.message ?? 'Failed to fetch subscription', loading: false });
    }
  },

  fetchPayments: async (params) => {
    set({ loading: true, error: null });
    try {
      const payments = await billingService.getPaymentHistory(params);
      set({ payments, loading: false });
    } catch (err: any) {
      set({ error: err?.response?.data?.detail ?? err.message ?? 'Failed to fetch payment history', loading: false });
    }
  },

  createCheckout: async (data) => {
    set({ loading: true, error: null });
    try {
      const { checkout_url } = await billingService.createCheckoutSession(data);
      set({ loading: false });
      return checkout_url;
    } catch (err: any) {
      set({ error: err?.response?.data?.detail ?? err.message ?? 'Failed to create checkout session', loading: false });
      throw err;
    }
  },

  openPortal: async () => {
    set({ loading: true, error: null });
    try {
      const { portal_url } = await billingService.createPortalSession();
      set({ loading: false });
      window.open(portal_url, '_blank');
    } catch (err: any) {
      set({ error: err?.response?.data?.detail ?? err.message ?? 'Failed to open billing portal', loading: false });
    }
  },

  previewChange: async (planId, interval) => {
    set({ loading: true, error: null });
    try {
      const preview = await billingService.previewPlanChange({ plan_id: planId, interval });
      set({ loading: false });
      return preview;
    } catch (err: any) {
      set({ error: err?.response?.data?.detail ?? err.message ?? 'Failed to preview plan change', loading: false });
      throw err;
    }
  },

  reset: () => set(initialState),
}));
