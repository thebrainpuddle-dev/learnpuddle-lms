// src/services/razorpayService.ts
//
// Razorpay payment integration service for Indian market.
// The Razorpay SDK is loaded dynamically via script tag (not npm).

import api from '../config/api';

// ── Razorpay Window Declaration ──────────────────────────────────────

declare global {
  interface Window {
    Razorpay: new (options: RazorpayCheckoutOptions) => RazorpayInstance;
  }
}

// ── Types ────────────────────────────────────────────────────────────

export interface RazorpayOrder {
  id: string;
  amount: number; // in paise (smallest currency unit)
  currency: string;
  status: 'created' | 'attempted' | 'paid';
  receipt?: string;
}

export interface RazorpayPaymentResponse {
  razorpay_payment_id: string;
  razorpay_order_id: string;
  razorpay_signature: string;
}

export interface RazorpayCheckoutOptions {
  key: string;
  amount: number;
  currency: string;
  name: string;
  description: string;
  order_id: string;
  handler: (response: RazorpayPaymentResponse) => void;
  prefill?: {
    name?: string;
    email?: string;
    contact?: string;
  };
  theme?: {
    color?: string;
  };
  modal?: {
    ondismiss?: () => void;
  };
}

export interface RazorpayInstance {
  open: () => void;
  close: () => void;
  on: (event: string, handler: (response: any) => void) => void;
}

export interface Plan {
  id: string;
  name: string;
  plan_code: string;
  description: string;
  price_monthly: number; // in INR (rupees, not paise)
  price_yearly: number;  // in INR (rupees, not paise)
  is_recommended: boolean;
  is_custom_pricing: boolean;
  features: string[];
  limits: {
    max_teachers: number;
    max_courses: number;
    max_storage_gb: number;
  };
  sort_order: number;
}

export interface CurrentPlanInfo {
  plan: Plan;
  status: 'active' | 'trial' | 'expired' | 'canceled';
  renewal_date: string | null;
  trial_end_date: string | null;
  usage: {
    teachers_used: number;
    teachers_max: number;
    courses_used: number;
    courses_max: number;
    storage_used_gb: number;
    storage_max_gb: number;
  };
}

export interface Invoice {
  id: string;
  invoice_number: string;
  date: string;
  amount: number; // in INR
  tax_amount: number; // GST amount
  total_amount: number; // amount + tax
  status: 'paid' | 'pending' | 'failed' | 'refunded';
  payment_method: string;
  download_url: string | null;
  razorpay_payment_id: string | null;
}

// ── SDK Loader ───────────────────────────────────────────────────────

let sdkLoadPromise: Promise<void> | null = null;

/**
 * Dynamically loads the Razorpay checkout script if not already loaded.
 */
export function loadRazorpaySDK(): Promise<void> {
  if (window.Razorpay) {
    return Promise.resolve();
  }

  if (sdkLoadPromise) {
    return sdkLoadPromise;
  }

  sdkLoadPromise = new Promise<void>((resolve, reject) => {
    const script = document.createElement('script');
    script.src = 'https://checkout.razorpay.com/v1/checkout.js';
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => {
      sdkLoadPromise = null;
      reject(new Error('Failed to load Razorpay SDK'));
    };
    document.head.appendChild(script);
  });

  return sdkLoadPromise;
}

// ── API Service ──────────────────────────────────────────────────────

export const razorpayService = {
  /**
   * Fetch available subscription plans.
   */
  async getPlans(): Promise<Plan[]> {
    // TODO: Update endpoint when backend is ready
    const res = await api.get('/billing/plans/');
    return res.data.results ?? res.data;
  },

  /**
   * Fetch the current tenant's active plan with usage metrics.
   */
  async getCurrentPlan(): Promise<CurrentPlanInfo> {
    // TODO: Update endpoint when backend is ready
    const res = await api.get('/billing/current-plan/');
    return res.data;
  },

  /**
   * Create a Razorpay order on the backend for a plan upgrade.
   * The backend creates the order via Razorpay API and returns order details + key.
   */
  async createOrder(planId: string): Promise<RazorpayOrder & { razorpay_key: string }> {
    // TODO: Update endpoint when backend is ready
    const res = await api.post('/billing/razorpay/create-order/', { plan_id: planId });
    return res.data;
  },

  /**
   * Verify payment with the backend after Razorpay checkout success.
   * Backend verifies the signature using Razorpay secret key.
   */
  async verifyPayment(response: RazorpayPaymentResponse): Promise<{ success: boolean; message: string }> {
    // TODO: Update endpoint when backend is ready
    const res = await api.post('/billing/razorpay/verify-payment/', response);
    return res.data;
  },

  /**
   * Fetch invoice history for the current tenant.
   */
  async getInvoices(params?: { page?: number }): Promise<Invoice[]> {
    // TODO: Update endpoint when backend is ready
    const res = await api.get('/billing/invoices/', { params });
    return res.data.results ?? res.data;
  },
};
