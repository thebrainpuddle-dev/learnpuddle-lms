// src/pages/admin/BillingPage.tsx
//
// Billing page with Razorpay + UPI integration for the Indian market.
// Sections: Current Plan, Plan Comparison, Invoice History.

import { useEffect, useState, useCallback } from 'react';
import {
  razorpayService,
  loadRazorpaySDK,
  type Plan,
  type CurrentPlanInfo,
  type Invoice,
  type RazorpayPaymentResponse,
} from '../../services/razorpayService';

// ── Helpers ──────────────────────────────────────────────────────────

function formatDate(dateStr: string | null) {
  if (!dateStr) return '\u2014';
  return new Date(dateStr).toLocaleDateString('en-IN', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

function formatINR(amount: number) {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount);
}

const STATUS_COLORS: Record<string, string> = {
  active: 'bg-green-100 text-green-800',
  paid: 'bg-green-100 text-green-800',
  trial: 'bg-yellow-100 text-yellow-800',
  pending: 'bg-yellow-100 text-yellow-800',
  expired: 'bg-red-100 text-red-800',
  canceled: 'bg-red-100 text-red-800',
  failed: 'bg-red-100 text-red-800',
  refunded: 'bg-blue-100 text-blue-800',
};

// ── Loading Spinner ──────────────────────────────────────────────────

function Spinner() {
  return (
    <div className="flex justify-center py-12">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600" />
    </div>
  );
}

// ── Usage Progress Bar ───────────────────────────────────────────────

function UsageBar({
  label,
  used,
  max,
  unit,
}: {
  label: string;
  used: number;
  max: number;
  unit: string;
}) {
  const percentage = max > 0 ? Math.min((used / max) * 100, 100) : 0;
  const isNearLimit = percentage >= 80;
  const isAtLimit = percentage >= 95;

  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <span className="text-sm font-medium text-gray-700">{label}</span>
        <span className="text-sm text-gray-500">
          {used} / {max} {unit}
        </span>
      </div>
      <div className="w-full bg-gray-200 rounded-full h-2.5">
        <div
          className={`h-2.5 rounded-full transition-all ${
            isAtLimit
              ? 'bg-red-500'
              : isNearLimit
              ? 'bg-yellow-500'
              : 'bg-indigo-600'
          }`}
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  );
}

// ── Section: Current Plan ────────────────────────────────────────────

function CurrentPlanSection({
  currentPlan,
  loading,
}: {
  currentPlan: CurrentPlanInfo | null;
  loading: boolean;
}) {
  if (loading && !currentPlan) return <Spinner />;

  if (!currentPlan) {
    return (
      <div className="text-center py-16 bg-white rounded-xl border border-gray-200">
        <svg
          className="h-12 w-12 mx-auto mb-3 text-gray-300"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d="M2.25 8.25h19.5M2.25 9h19.5m-16.5 5.25h6m-6 2.25h3m-3.75 3h15a2.25 2.25 0 002.25-2.25V6.75A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25v10.5A2.25 2.25 0 004.5 19.5z"
          />
        </svg>
        <p className="text-lg font-medium text-gray-900">No Active Plan</p>
        <p className="text-sm text-gray-500 mt-1">
          Choose a plan below to get started.
        </p>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
      <h2 className="text-lg font-semibold text-gray-900 mb-6">Current Plan</h2>

      {/* Plan info row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        <div>
          <p className="text-sm font-medium text-gray-500">Plan</p>
          <p className="mt-1 text-lg font-semibold text-gray-900">
            {currentPlan.plan.name}
          </p>
        </div>
        <div>
          <p className="text-sm font-medium text-gray-500">Status</p>
          <p className="mt-1">
            <span
              className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                STATUS_COLORS[currentPlan.status] ?? 'bg-gray-100 text-gray-800'
              }`}
            >
              {currentPlan.status === 'trial' ? 'Trial' : currentPlan.status.charAt(0).toUpperCase() + currentPlan.status.slice(1)}
            </span>
          </p>
        </div>
        <div>
          <p className="text-sm font-medium text-gray-500">Renewal Date</p>
          <p className="mt-1 text-sm text-gray-900">
            {formatDate(currentPlan.renewal_date)}
          </p>
        </div>
        {currentPlan.status === 'trial' && currentPlan.trial_end_date && (
          <div>
            <p className="text-sm font-medium text-gray-500">Trial Ends</p>
            <p className="mt-1 text-sm text-yellow-700 font-medium">
              {formatDate(currentPlan.trial_end_date)}
            </p>
          </div>
        )}
      </div>

      {/* Usage metrics */}
      <div className="space-y-4">
        <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wider">
          Usage
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <UsageBar
            label="Teachers"
            used={currentPlan.usage.teachers_used}
            max={currentPlan.usage.teachers_max}
            unit=""
          />
          <UsageBar
            label="Courses"
            used={currentPlan.usage.courses_used}
            max={currentPlan.usage.courses_max}
            unit=""
          />
          <UsageBar
            label="Storage"
            used={currentPlan.usage.storage_used_gb}
            max={currentPlan.usage.storage_max_gb}
            unit="GB"
          />
        </div>
      </div>
    </div>
  );
}

// ── Section: Plan Comparison ─────────────────────────────────────────

function PlanComparisonSection({
  plans,
  currentPlanId,
  loading,
  onUpgrade,
  upgradeLoading,
}: {
  plans: Plan[];
  currentPlanId: string | null;
  loading: boolean;
  onUpgrade: (plan: Plan) => void;
  upgradeLoading: string | null;
}) {
  if (loading && plans.length === 0) return <Spinner />;

  if (plans.length === 0) {
    return (
      <div className="text-center py-12 text-gray-500 bg-white rounded-xl border border-gray-200">
        <p className="font-medium">No plans available.</p>
        <p className="text-sm mt-1">Plans will appear here once configured.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold text-gray-900">Plans</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {plans.map((plan) => {
          const isCurrentPlan = currentPlanId === plan.id;

          return (
            <div
              key={plan.id}
              className={`relative bg-white rounded-xl border shadow-sm p-6 flex flex-col ${
                plan.is_recommended
                  ? 'border-indigo-500 ring-2 ring-indigo-500'
                  : 'border-gray-200'
              }`}
            >
              {/* Recommended badge */}
              {plan.is_recommended && (
                <div className="absolute -top-3 left-1/2 -translate-x-1/2">
                  <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold bg-indigo-600 text-white">
                    Recommended
                  </span>
                </div>
              )}

              {/* Current plan badge */}
              {isCurrentPlan && (
                <div className="absolute top-4 right-4">
                  <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                    Current Plan
                  </span>
                </div>
              )}

              <div className="flex-1">
                <h3 className="text-lg font-semibold text-gray-900">
                  {plan.name}
                </h3>
                {plan.description && (
                  <p className="mt-1 text-sm text-gray-500">
                    {plan.description}
                  </p>
                )}

                {/* Price */}
                <div className="mt-4">
                  {plan.is_custom_pricing ? (
                    <p className="text-2xl font-bold text-gray-900">Custom</p>
                  ) : (
                    <div>
                      <div className="flex items-baseline">
                        <span className="text-3xl font-bold text-gray-900">
                          {formatINR(plan.price_monthly)}
                        </span>
                        <span className="ml-1 text-sm text-gray-500">/mo</span>
                      </div>
                      <p className="text-xs text-gray-400 mt-0.5">
                        or {formatINR(plan.price_yearly)}/year (save{' '}
                        {Math.round(
                          (1 - plan.price_yearly / (plan.price_monthly * 12)) *
                            100
                        )}
                        %)
                      </p>
                    </div>
                  )}
                </div>

                {/* Limits */}
                {plan.limits && (
                  <div className="mt-4 space-y-1">
                    <p className="text-xs text-gray-500">
                      Up to {plan.limits.max_teachers} teachers &bull;{' '}
                      {plan.limits.max_courses} courses &bull;{' '}
                      {plan.limits.max_storage_gb} GB storage
                    </p>
                  </div>
                )}

                {/* Features */}
                {plan.features && plan.features.length > 0 && (
                  <ul className="mt-6 space-y-2">
                    {plan.features.map((feature, idx) => (
                      <li
                        key={idx}
                        className="flex items-start text-sm text-gray-700"
                      >
                        <svg
                          className="h-4 w-4 text-green-500 mr-2 mt-0.5 flex-shrink-0"
                          fill="none"
                          viewBox="0 0 24 24"
                          stroke="currentColor"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M5 13l4 4L19 7"
                          />
                        </svg>
                        {feature}
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              {/* Action button */}
              <div className="mt-6">
                {isCurrentPlan ? (
                  <div className="w-full py-2.5 text-center text-sm font-medium text-indigo-600 bg-indigo-50 rounded-lg">
                    Current Plan
                  </div>
                ) : plan.is_custom_pricing ? (
                  <a
                    href="mailto:sales@learnpuddle.com"
                    className="block w-full py-2.5 text-center text-sm font-medium text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors"
                  >
                    Contact Sales
                  </a>
                ) : (
                  <button
                    onClick={() => onUpgrade(plan)}
                    disabled={upgradeLoading === plan.id}
                    className={`w-full py-2.5 text-sm font-medium rounded-lg transition-colors disabled:opacity-50 ${
                      plan.is_recommended
                        ? 'bg-indigo-600 text-white hover:bg-indigo-700'
                        : 'bg-white text-indigo-600 border border-indigo-600 hover:bg-indigo-50'
                    }`}
                  >
                    {upgradeLoading === plan.id ? 'Processing...' : 'Upgrade'}
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Section: Invoice History ─────────────────────────────────────────

function InvoiceHistorySection({
  invoices,
  loading,
}: {
  invoices: Invoice[];
  loading: boolean;
}) {
  if (loading && invoices.length === 0) return <Spinner />;

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold text-gray-900">Invoice History</h2>

      {invoices.length === 0 ? (
        <div className="text-center py-12 text-gray-500 bg-white rounded-xl border border-gray-200">
          <svg
            className="h-12 w-12 mx-auto mb-3 text-gray-300"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M9 14l6-6m-5.5.5h.01m4.99 5h.01M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16l3.5-2 3.5 2 3.5-2 3.5 2z"
            />
          </svg>
          <p className="font-medium">No invoices yet.</p>
          <p className="text-sm mt-1">
            Invoices will appear here after your first payment.
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto bg-white rounded-xl border border-gray-200 shadow-sm">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Date
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Invoice #
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Amount
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  GST
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Total
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Status
                </th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Download
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-100">
              {invoices.map((invoice) => (
                <tr key={invoice.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 text-sm text-gray-700 whitespace-nowrap">
                    {formatDate(invoice.date)}
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-900 font-medium whitespace-nowrap">
                    {invoice.invoice_number}
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-700 whitespace-nowrap">
                    {formatINR(invoice.amount)}
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-700 whitespace-nowrap">
                    {formatINR(invoice.tax_amount)}
                  </td>
                  <td className="px-4 py-3 text-sm font-medium text-gray-900 whitespace-nowrap">
                    {formatINR(invoice.total_amount)}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                        STATUS_COLORS[invoice.status] ??
                        'bg-gray-100 text-gray-800'
                      }`}
                    >
                      {invoice.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right whitespace-nowrap">
                    {invoice.download_url ? (
                      <a
                        href={invoice.download_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-sm text-indigo-600 hover:text-indigo-800 font-medium transition-colors"
                      >
                        PDF
                      </a>
                    ) : (
                      <span className="text-sm text-gray-400">\u2014</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Main Page ────────────────────────────────────────────────────────

export function BillingPage() {
  const [currentPlan, setCurrentPlan] = useState<CurrentPlanInfo | null>(null);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [upgradeLoading, setUpgradeLoading] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [planData, plansData, invoicesData] = await Promise.allSettled([
        razorpayService.getCurrentPlan(),
        razorpayService.getPlans(),
        razorpayService.getInvoices(),
      ]);

      if (planData.status === 'fulfilled') {
        setCurrentPlan(planData.value);
      }
      if (plansData.status === 'fulfilled') {
        setPlans(plansData.value);
      }
      if (invoicesData.status === 'fulfilled') {
        setInvoices(invoicesData.value);
      }

      // Only set error if all requests failed
      if (
        planData.status === 'rejected' &&
        plansData.status === 'rejected' &&
        invoicesData.status === 'rejected'
      ) {
        setError('Failed to load billing data. Please try again.');
      }
    } catch {
      setError('Failed to load billing data. Please try again.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleUpgrade = async (plan: Plan) => {
    setUpgradeLoading(plan.id);
    setError(null);

    try {
      // Load Razorpay SDK
      await loadRazorpaySDK();

      // Create order on backend
      const order = await razorpayService.createOrder(plan.id);

      // Open Razorpay checkout
      const razorpay = new window.Razorpay({
        key: order.razorpay_key,
        amount: order.amount,
        currency: order.currency,
        name: 'LearnPuddle',
        description: `${plan.name} Plan Subscription`,
        order_id: order.id,
        handler: async (response: RazorpayPaymentResponse) => {
          try {
            const result = await razorpayService.verifyPayment(response);
            if (result.success) {
              setSuccessMessage(
                `Successfully upgraded to ${plan.name} plan! Your payment has been processed.`
              );
              setTimeout(() => setSuccessMessage(null), 5000);
              // Refresh billing data
              fetchData();
            } else {
              setError(
                result.message || 'Payment verification failed. Please contact support.'
              );
            }
          } catch {
            setError(
              'Payment verification failed. If amount was deducted, please contact support.'
            );
          }
        },
        prefill: {
          // Will be populated from user context on backend
        },
        theme: {
          color: '#4F46E5', // indigo-600
        },
        modal: {
          ondismiss: () => {
            setUpgradeLoading(null);
          },
        },
      });

      razorpay.open();
    } catch (err: any) {
      setError(
        err?.response?.data?.detail ??
          err.message ??
          'Failed to initiate payment. Please try again.'
      );
    } finally {
      setUpgradeLoading(null);
    }
  };

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Billing</h1>
        <p className="mt-1 text-sm text-gray-500">
          Manage your subscription, compare plans, and view invoices.
        </p>
      </div>

      {/* Error message */}
      {error && (
        <div className="rounded-lg bg-red-50 border border-red-200 p-4">
          <div className="flex">
            <svg
              className="h-5 w-5 text-red-400 flex-shrink-0 mr-3 mt-0.5"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z"
              />
            </svg>
            <p className="text-sm text-red-700">{error}</p>
          </div>
        </div>
      )}

      {/* Success message */}
      {successMessage && (
        <div className="rounded-lg bg-green-50 border border-green-200 p-4">
          <div className="flex">
            <svg
              className="h-5 w-5 text-green-400 flex-shrink-0 mr-3 mt-0.5"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M5 13l4 4L19 7"
              />
            </svg>
            <p className="text-sm text-green-700">{successMessage}</p>
          </div>
        </div>
      )}

      {/* Payment methods info banner */}
      <div className="bg-indigo-50 border border-indigo-100 rounded-xl p-4">
        <div className="flex items-center">
          <svg
            className="h-5 w-5 text-indigo-500 mr-3 flex-shrink-0"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M2.25 8.25h19.5M2.25 9h19.5m-16.5 5.25h6m-6 2.25h3m-3.75 3h15a2.25 2.25 0 002.25-2.25V6.75A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25v10.5A2.25 2.25 0 004.5 19.5z"
            />
          </svg>
          <p className="text-sm text-indigo-700">
            We accept <strong>UPI</strong>, <strong>Credit/Debit Cards</strong>,{' '}
            <strong>Net Banking</strong>, and <strong>Wallets</strong> via
            Razorpay secure checkout.
          </p>
        </div>
      </div>

      {/* Current Plan */}
      <CurrentPlanSection currentPlan={currentPlan} loading={loading} />

      {/* Plan Comparison */}
      <PlanComparisonSection
        plans={plans}
        currentPlanId={currentPlan?.plan?.id ?? null}
        loading={loading}
        onUpgrade={handleUpgrade}
        upgradeLoading={upgradeLoading}
      />

      {/* Invoice History */}
      <InvoiceHistorySection invoices={invoices} loading={loading} />
    </div>
  );
}
