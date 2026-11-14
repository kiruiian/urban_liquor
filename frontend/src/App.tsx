import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowLeft,
  ArrowDownLeft,
  ArrowRight,
  BarChart3,
  BadgeCheck,
  Banknote,
  CalendarDays,
  Check,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  LoaderCircle,
  LogOut,
  Minus,
  Package,
  Plus,
  ReceiptText,
  Search,
  ShieldCheck,
  ShoppingBag,
  Smartphone,
  Truck,
  Printer,
  Users,
  UserCheck,
  UserX,
  Pencil,
  Wine,
  X,
} from "lucide-react";

const API_URL = (import.meta.env.VITE_API_URL || "/api/v1").replace(/\/$/, "");
const CURRENCY = "KES";

type Staff = {
  id: number;
  username: string;
  full_name: string;
  role: "admin" | "cashier";
  is_active: boolean;
};

type Product = {
  id: number;
  barcode: string | null;
  name: string;
  category: string | null;
  unit_price: string;
  stock_quantity: string;
  low_stock_threshold: string;
  is_active: boolean;
};

type InventoryInsights = {
  currency: string;
  stock_value: string;
  period_days: number;
  fast_movers: {
    id: number;
    name: string;
    sku: string;
    unit_price: string;
    stock_quantity: string;
    quantity_sold: string;
  }[];
};

type Sale = {
  id: number;
  subtotal: string;
  total: string;
  currency: string;
  created_at: string;
  items: { id: number; product_name: string; sku: string; quantity: string; unit_price: string; line_total: string }[];
  payments: { id: number; method: string; amount: string; cash_received: string; change_given: string; mpesa_reference: string | null }[];
};

type SalesSummary = {
  date: string;
  period: "daily" | "weekly" | "monthly";
  start_date: string;
  end_date: string;
  sale_count: number;
  total: string;
  cash_total: string;
  mpesa_total: string;
};

type CartLine = { product: Product; quantity: number };

type Supplier = {
  id: number;
  name: string;
  contact_name: string | null;
  phone: string | null;
  email: string | null;
  address: string | null;
  is_active: boolean;
  created_at: string;
};

type SupplierReceipt = {
  id: number;
  supplier_id: number;
  supplier_name: string;
  supplier_reference: string | null;
  received_by_name: string;
  received_at: string;
  items: { id: number; product_id: number; product_name: string; sku: string; quantity_received: string }[];
};

type WholesaleCustomer = {
  id: number;
  name: string;
  contact_name: string | null;
  phone: string | null;
  email: string | null;
  address: string | null;
  is_active: boolean;
  created_at: string;
};

type WholesaleSale = {
  id: number;
  customer_id: number;
  customer_name: string;
  delivery_reference: string | null;
  created_by_name: string;
  currency: string;
  total: string;
  created_at: string;
  amount_paid: string;
  balance_due: string;
  payment_status: "unpaid" | "partial" | "paid";
  items: { id: number; product_id: number; product_name: string; sku: string; quantity: string; unit_price: string; line_total: string }[];
  payments: { id: number; method: string; amount: string; cash_received: string; change_given: string; mpesa_reference: string | null }[];
};

async function request<T>(path: string, token: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...init?.headers,
    },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail || `Request failed (${response.status})`);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

function money(amount: number | string): string {
  return new Intl.NumberFormat("en-KE", {
    style: "currency",
    currency: CURRENCY,
    maximumFractionDigits: 2,
  }).format(Number(amount));
}

function localDateValue(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function reportDateRange(anchorDate: string, period: SalesSummary["period"]): [string, string] {
  const [year, month, day] = anchorDate.split("-").map(Number);
  const anchor = new Date(year, month - 1, day);
  if (period === "daily") return [anchorDate, anchorDate];
  if (period === "weekly") {
    const start = new Date(year, month - 1, day - ((anchor.getDay() + 6) % 7));
    const end = new Date(start);
    end.setDate(start.getDate() + 6);
    return [localDateValue(start), localDateValue(end)];
  }
  return [
    localDateValue(new Date(year, month - 1, 1)),
    localDateValue(new Date(year, month, 0)),
  ];
}

function formatSaleTime(value: string): string {
  return new Intl.DateTimeFormat("en-KE", {
    timeZone: "Africa/Nairobi",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function formatReceiptDate(value: string): string {
  return new Intl.DateTimeFormat("en-KE", {
    timeZone: "Africa/Nairobi",
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

type StaffForm = {
  username: string;
  full_name: string;
  password: string;
  role: "admin" | "cashier";
};

function StaffManagement({
  token,
  currentStaff,
  onBack,
}: {
  token: string;
  currentStaff: Staff;
  onBack: () => void;
}) {
  const [staffMembers, setStaffMembers] = useState<Staff[]>([]);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<StaffForm>({
    username: "",
    full_name: "",
    password: "",
    role: "cashier",
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [busyStaffId, setBusyStaffId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const loadStaff = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setStaffMembers(await request<Staff[]>("/auth/staff", token));
      return true;
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to load staff");
      return false;
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void loadStaff();
  }, [loadStaff]);

  function resetForm() {
    setEditingId(null);
    setForm({ username: "", full_name: "", password: "", role: "cashier" });
  }

  function editMember(member: Staff) {
    setError("");
    setNotice("");
    setEditingId(member.id);
    setForm({
      username: member.username,
      full_name: member.full_name,
      password: "",
      role: member.role,
    });
  }

  async function submitStaff(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError("");
    setNotice("");
    const editing = editingId !== null;
    const payload = {
      username: form.username.trim(),
      full_name: form.full_name.trim(),
      role: form.role,
      ...(!editing ? { password: form.password } : {}),
    };
    try {
      await request<Staff>(editing ? `/auth/staff/${editingId}` : "/auth/staff", token, {
        method: editing ? "PATCH" : "POST",
        body: JSON.stringify(payload),
      });
      const refreshed = await loadStaff();
      resetForm();
      setNotice(
        refreshed
          ? editing ? "Staff account updated." : "Staff account created."
          : "Changes saved, but the staff list could not be refreshed.",
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to save staff account");
    } finally {
      setSaving(false);
    }
  }

  async function toggleActive(member: Staff) {
    setBusyStaffId(member.id);
    setError("");
    setNotice("");
    try {
      await request<Staff>(`/auth/staff/${member.id}`, token, {
        method: "PATCH",
        body: JSON.stringify({ is_active: !member.is_active }),
      });
      const refreshed = await loadStaff();
      setNotice(
        refreshed
          ? `${member.full_name} ${member.is_active ? "deactivated" : "activated"}.`
          : "Changes saved, but the staff list could not be refreshed.",
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to update staff account");
    } finally {
      setBusyStaffId(null);
    }
  }

  const activeAdminCount = staffMembers.filter(
    (member) => member.role === "admin" && member.is_active,
  ).length;
  const editingMember = staffMembers.find((member) => member.id === editingId);
  const lastActiveAdminEditing =
    editingMember?.role === "admin" && editingMember.is_active && activeAdminCount === 1;

  return (
    <section className="staff-page">
      <div className="page-heading staff-page-heading">
        <div>
          <span className="eyebrow">STORE ACCESS</span>
          <h1>Staff &amp; roles</h1>
          <p className="muted">Manage who can access the point of sale and their permissions.</p>
        </div>
        <button className="secondary-button" onClick={onBack}><ArrowLeft size={16} /> Back to POS</button>
      </div>

      <div className="staff-layout">
        <section className="staff-card">
          <div className="staff-card-heading">
            <div><h2>Staff accounts</h2><p>{staffMembers.length} accounts</p></div>
            <Users size={19} />
          </div>
          {error && <div className="alert error"><CircleAlert size={15} />{error}</div>}
          {notice && <div className="alert success"><BadgeCheck size={15} />{notice}</div>}
          {loading ? (
            <div className="staff-loading"><LoaderCircle className="spin" size={18} /> Loading staff...</div>
          ) : staffMembers.length === 0 ? (
            <div className="staff-empty">No staff accounts found.</div>
          ) : (
            <div className="staff-table-wrap">
              <table className="staff-table">
                <thead><tr><th>Staff member</th><th>Role</th><th>Status</th><th>Actions</th></tr></thead>
                <tbody>
                  {staffMembers.map((member) => {
                    const cannotDeactivate =
                      member.id === currentStaff.id ||
                      (member.role === "admin" && member.is_active && activeAdminCount <= 1);
                    return (
                      <tr key={member.id}>
                        <td><b>{member.full_name}</b><small>@{member.username}</small></td>
                        <td><span className={`role-badge ${member.role}`}>{member.role}</span></td>
                        <td><span className={`status-badge ${member.is_active ? "active" : "inactive"}`}>{member.is_active ? "Active" : "Inactive"}</span></td>
                        <td>
                          <div className="staff-actions">
                            <button className="staff-action" onClick={() => editMember(member)} aria-label={`Edit ${member.full_name}`} title="Edit account"><Pencil size={15} /></button>
                            <button
                              className={`staff-action ${member.is_active ? "deactivate" : "activate"}`}
                              onClick={() => void toggleActive(member)}
                              disabled={busyStaffId === member.id || cannotDeactivate}
                              aria-label={`${member.is_active ? "Deactivate" : "Activate"} ${member.full_name}`}
                              title={cannotDeactivate ? "You cannot deactivate yourself or the last active admin" : `${member.is_active ? "Deactivate" : "Activate"} account`}
                            >
                              {busyStaffId === member.id ? <LoaderCircle className="spin" size={15} /> : member.is_active ? <UserX size={15} /> : <UserCheck size={15} />}
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <form className="staff-card staff-form" onSubmit={submitStaff}>
          <div className="staff-card-heading">
            <div><h2>{editingId === null ? "Add staff member" : "Edit staff member"}</h2><p>Admins can manage products and staff.</p></div>
            <ShieldCheck size={19} />
          </div>
          <label>Full name<input value={form.full_name} onChange={(event) => setForm({ ...form, full_name: event.target.value })} maxLength={120} required /></label>
          <label>Username<input value={form.username} onChange={(event) => setForm({ ...form, username: event.target.value })} minLength={3} maxLength={64} pattern="[a-zA-Z0-9._-]+" autoComplete="off" required /></label>
          {editingId === null && <label>Temporary password<input type="password" value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} minLength={12} maxLength={256} autoComplete="new-password" required /><small className="field-hint">At least 12 characters. The staff member can sign in with this password.</small></label>}
          <label>Role<select value={form.role} onChange={(event) => setForm({ ...form, role: event.target.value as StaffForm["role"] })} disabled={Boolean(lastActiveAdminEditing)}><option value="cashier">Cashier</option><option value="admin">Admin</option></select></label>
          {lastActiveAdminEditing && <p className="field-hint">The last active admin cannot be demoted or deactivated.</p>}
          <div className="staff-form-actions">
            {editingId !== null && <button type="button" className="secondary-button" onClick={resetForm}>Cancel</button>}
            <button type="submit" className="primary-button" disabled={saving}>{saving ? <LoaderCircle className="spin" size={17} /> : editingId === null ? "Create account" : "Save changes"}</button>
          </div>
        </form>
      </div>
    </section>
  );
}

type ProductForm = {
  barcode: string;
  name: string;
  category: string;
  unit_price: string;
  initial_stock: string;
  low_stock_threshold: string;
};

function InventoryManagement({
  token,
  onBack,
  onProductsChanged,
}: {
  token: string;
  onBack: () => void;
  onProductsChanged: () => Promise<void>;
}) {
  const [inventory, setInventory] = useState<Product[]>([]);
  const [insights, setInsights] = useState<InventoryInsights | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [stockProductId, setStockProductId] = useState<number | null>(null);
  const [form, setForm] = useState<ProductForm>({
    barcode: "",
    name: "",
    category: "",
    unit_price: "",
    initial_stock: "0",
    low_stock_threshold: "0",
  });
  const [stockDelta, setStockDelta] = useState("");
  const [stockReason, setStockReason] = useState("");
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<"all" | "active" | "inactive" | "low">("all");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [busyProductId, setBusyProductId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const loadProducts = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [products, inventoryInsights] = await Promise.all([
        request<Product[]>("/inventory/products?active_only=false&limit=200", token),
        request<InventoryInsights>("/inventory/insights", token),
      ]);
      setInventory(products);
      setInsights(inventoryInsights);
      return true;
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to load products");
      return false;
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void loadProducts();
  }, [loadProducts]);

  const visibleProducts = useMemo(() => {
    const query = search.trim().toLowerCase();
    return inventory.filter((product) => {
      const matchesSearch = !query ||
        [product.name, product.barcode || "", product.category || ""]
          .some((value) => value.toLowerCase().includes(query));
      const matchesFilter =
        filter === "all" ||
        (filter === "active" && product.is_active) ||
        (filter === "inactive" && !product.is_active) ||
        (filter === "low" && Number(product.stock_quantity) <= Number(product.low_stock_threshold));
      return matchesSearch && matchesFilter;
    });
  }, [filter, inventory, search]);

  function resetForm() {
    setEditingId(null);
    setForm({
      barcode: "",
      name: "",
      category: "",
      unit_price: "",
      initial_stock: "0",
      low_stock_threshold: "0",
    });
  }

  function editProduct(product: Product) {
    setError("");
    setNotice("");
    setEditingId(product.id);
    setForm({
      barcode: product.barcode || "",
      name: product.name,
      category: product.category || "",
      unit_price: product.unit_price,
      initial_stock: "0",
      low_stock_threshold: product.low_stock_threshold,
    });
  }

  async function refreshAfterChange(successMessage: string) {
    const refreshed = await loadProducts();
    await onProductsChanged();
    setNotice(
      refreshed ? successMessage : "Changes saved, but the product list could not be refreshed.",
    );
  }

  async function submitProduct(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError("");
    setNotice("");
    const editing = editingId !== null;
    const payload = {
      barcode: form.barcode.trim() || null,
      name: form.name.trim(),
      category: form.category.trim() || null,
      unit_price: form.unit_price,
      low_stock_threshold: form.low_stock_threshold || "0",
      ...(!editing ? { initial_stock: form.initial_stock || "0" } : {}),
    };
    try {
      await request<Product>(
        editing ? `/inventory/products/${editingId}` : "/inventory/products",
        token,
        { method: editing ? "PATCH" : "POST", body: JSON.stringify(payload) },
      );
      await refreshAfterChange(editing ? "Product updated." : "Product created.");
      resetForm();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to save product");
    } finally {
      setSaving(false);
    }
  }

  async function adjustStock(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (Number(stockDelta) === 0) {
      setError("Enter a non-zero stock change.");
      return;
    }
    const product = inventory.find((item) => item.id === stockProductId);
    if (!product) return;
    setSaving(true);
    setError("");
    setNotice("");
    try {
      await request<Product>(`/inventory/products/${product.id}/stock-adjustments`, token, {
        method: "POST",
        body: JSON.stringify({
          quantity_delta: stockDelta,
          reason: stockReason.trim(),
        }),
      });
      await refreshAfterChange(`${product.name} stock adjusted.`);
      setStockDelta("");
      setStockReason("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to adjust stock");
    } finally {
      setSaving(false);
    }
  }

  async function toggleActive(product: Product) {
    setBusyProductId(product.id);
    setError("");
    setNotice("");
    try {
      await request<Product>(`/inventory/products/${product.id}`, token, {
        method: "PATCH",
        body: JSON.stringify({ is_active: !product.is_active }),
      });
      await refreshAfterChange(
        `${product.name} ${product.is_active ? "deactivated" : "activated"}.`,
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to update product");
    } finally {
      setBusyProductId(null);
    }
  }

  const stockProduct = inventory.find((product) => product.id === stockProductId);

  return (
    <section className="staff-page">
      <div className="page-heading staff-page-heading">
        <div>
          <span className="eyebrow">CATALOG &amp; STOCK</span>
          <h1>Products &amp; inventory</h1>
          <p className="muted">Manage products, prices, and stock levels.</p>
        </div>
        <button className="secondary-button" onClick={onBack}><ArrowLeft size={16} /> Back to POS</button>
      </div>

      {error && <div className="alert error inventory-alert"><CircleAlert size={15} />{error}</div>}
      {notice && <div className="alert success inventory-alert"><BadgeCheck size={15} />{notice}</div>}

      <div className="inventory-insights">
        <section className="inventory-value-card">
          <div className="inventory-value-icon"><Package size={19} /></div>
          <span>Current stock value</span>
          <strong>{insights ? money(insights.stock_value) : "—"}</strong>
          <small>Based on current selling prices</small>
        </section>
        <section className="staff-card inventory-fast-movers">
          <div className="staff-card-heading">
            <div><h2>Fast-moving products</h2><p>Most units sold in the last {insights?.period_days ?? 30} days · includes retail and wholesale</p></div>
            <BarChart3 size={19} />
          </div>
          {loading && !insights ? (
            <div className="staff-loading"><LoaderCircle className="spin" size={18} /> Loading sales trends...</div>
          ) : !insights?.fast_movers.length ? (
            <div className="staff-empty">No product sales recorded in the last 30 days.</div>
          ) : (
            <div className="staff-table-wrap">
              <table className="staff-table fast-movers-table">
                <thead><tr><th>Product</th><th>Sold</th><th>In stock</th><th>Suggested add</th><th></th></tr></thead>
                <tbody>
                  {insights.fast_movers.map((product) => (
                    <tr key={product.id}>
                      <td><b>{product.name}</b><small>{product.sku}</small></td>
                      <td>{product.quantity_sold}</td>
                      <td>{product.stock_quantity}</td>
                      <td>{product.quantity_sold}</td>
                      <td>
                        <button
                          type="button"
                          className="secondary-button fast-mover-restock"
                          onClick={() => {
                            setStockProductId(product.id);
                            setStockDelta(product.quantity_sold);
                            setStockReason(`Suggested restock: ${insights.period_days}-day sales`);
                          }}
                        >
                          <Plus size={14} /> Restock
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <small className="inventory-insight-note">Suggested add matches the quantity sold in this period; adjust it before saving if needed.</small>
        </section>
      </div>

      <div className="inventory-layout">
        <section className="staff-card">
          <div className="staff-card-heading">
            <div><h2>Product catalog</h2><p>{visibleProducts.length} of {inventory.length} products</p></div>
            <Package size={19} />
          </div>
          <div className="inventory-filterbar">
            <label className="search-box"><Search size={16} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search name or barcode..." /></label>
            <select aria-label="Filter products" value={filter} onChange={(event) => setFilter(event.target.value as typeof filter)}>
              <option value="all">All products</option>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
              <option value="low">Low stock</option>
            </select>
          </div>
          {loading ? (
            <div className="staff-loading"><LoaderCircle className="spin" size={18} /> Loading products...</div>
          ) : visibleProducts.length === 0 ? (
            <div className="staff-empty">No products match this filter.</div>
          ) : (
            <div className="staff-table-wrap">
              <table className="staff-table inventory-table">
                <thead><tr><th>Product</th><th>Price</th><th>Stock</th><th>Status</th><th>Actions</th></tr></thead>
                <tbody>
                  {visibleProducts.map((product) => {
                    const lowStock = Number(product.stock_quantity) <= Number(product.low_stock_threshold);
                    return (
                      <tr key={product.id}>
                        <td><b>{product.name}</b>{product.category && <small>{product.category}</small>}</td>
                        <td>{money(product.unit_price)}</td>
                        <td><span className={lowStock ? "stock low" : "stock"}>{product.stock_quantity}</span><small>Threshold: {product.low_stock_threshold}</small></td>
                        <td><span className={`status-badge ${product.is_active ? "active" : "inactive"}`}>{product.is_active ? "Active" : "Inactive"}</span></td>
                        <td>
                          <div className="staff-actions">
                            <button type="button" className="staff-action" onClick={() => editProduct(product)} aria-label={`Edit ${product.name}`} title="Edit product"><Pencil size={15} /></button>
                            <button type="button" className="staff-action activate" onClick={() => { setStockProductId(product.id); setStockDelta(""); setStockReason(""); }} aria-label={`Adjust stock for ${product.name}`} title="Adjust stock"><Plus size={16} /></button>
                            <button
                              type="button"
                              className={`staff-action ${product.is_active ? "deactivate" : "activate"}`}
                              onClick={() => void toggleActive(product)}
                              disabled={busyProductId === product.id}
                              aria-label={`${product.is_active ? "Deactivate" : "Activate"} ${product.name}`}
                              title={`${product.is_active ? "Deactivate" : "Activate"} product`}
                            >
                              {busyProductId === product.id ? <LoaderCircle className="spin" size={15} /> : product.is_active ? <UserX size={15} /> : <UserCheck size={15} />}
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <div className="inventory-side">
          <form className="staff-card staff-form" onSubmit={submitProduct}>
            <div className="staff-card-heading">
              <div><h2>{editingId === null ? "Add product" : "Edit product"}</h2><p>Prices are entered in KES.</p></div>
              <Package size={19} />
            </div>
            <label>Product name<input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} maxLength={160} required /></label>
            <label>Barcode <span className="optional-label">Optional</span><input value={form.barcode} onChange={(event) => setForm({ ...form, barcode: event.target.value })} maxLength={64} /></label>
            <label>Category <span className="optional-label">Optional</span><input value={form.category} onChange={(event) => setForm({ ...form, category: event.target.value })} maxLength={80} /></label>
            <label>Unit price (KES)<input type="number" min="0" step="0.01" value={form.unit_price} onChange={(event) => setForm({ ...form, unit_price: event.target.value })} required /></label>
            {editingId === null && <label>Initial stock<input type="number" min="0" step="0.001" value={form.initial_stock} onChange={(event) => setForm({ ...form, initial_stock: event.target.value })} required /></label>}
            <label>Low-stock alert at<input type="number" min="0" step="0.001" value={form.low_stock_threshold} onChange={(event) => setForm({ ...form, low_stock_threshold: event.target.value })} required /></label>
            <div className="staff-form-actions">
              {editingId !== null && <button type="button" className="secondary-button" onClick={resetForm}>Cancel</button>}
              <button type="submit" className="primary-button" disabled={saving}>{saving ? <LoaderCircle className="spin" size={17} /> : editingId === null ? "Create product" : "Save changes"}</button>
            </div>
          </form>

          {stockProduct && (
            <form className="staff-card staff-form" onSubmit={adjustStock}>
              <div className="staff-card-heading">
                <div><h2>Adjust stock</h2><p>{stockProduct.name} · current stock {stockProduct.stock_quantity}</p></div>
                <button type="button" className="staff-action" onClick={() => setStockProductId(null)} aria-label="Close stock adjustment"><X size={16} /></button>
              </div>
              <label>Quantity change<input type="number" step="0.001" value={stockDelta} onChange={(event) => setStockDelta(event.target.value)} placeholder="Positive to add, negative to remove" required /></label>
              <small className="field-hint">Use a negative amount to remove stock. Stock cannot fall below zero.</small>
              <label>Reason<input value={stockReason} onChange={(event) => setStockReason(event.target.value)} maxLength={200} required /></label>
              <button type="submit" className="primary-button" disabled={saving}>{saving ? <LoaderCircle className="spin" size={17} /> : "Save adjustment"}</button>
            </form>
          )}
        </div>
      </div>
    </section>
  );
}

type SupplierForm = {
  name: string;
  contact_name: string;
  phone: string;
  email: string;
  address: string;
  is_active: boolean;
};

type SupplierReceiptLineForm = { product_id: string; quantity_received: string };

function SuppliersManagement({
  token,
  products,
  onProductsChanged,
  onBack,
}: {
  token: string;
  products: Product[];
  onProductsChanged: () => Promise<void>;
  onBack: () => void;
}) {
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [receipts, setReceipts] = useState<SupplierReceipt[]>([]);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [supplierForm, setSupplierForm] = useState<SupplierForm>({
    name: "",
    contact_name: "",
    phone: "",
    email: "",
    address: "",
    is_active: true,
  });
  const [supplierId, setSupplierId] = useState("");
  const [supplierReference, setSupplierReference] = useState("");
  const [receiptLines, setReceiptLines] = useState<SupplierReceiptLineForm[]>([
    { product_id: "", quantity_received: "" },
  ]);
  const [loading, setLoading] = useState(true);
  const [savingSupplier, setSavingSupplier] = useState(false);
  const [savingReceipt, setSavingReceipt] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const loadData = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [supplierList, receiptList] = await Promise.all([
        request<Supplier[]>("/suppliers?active_only=false", token),
        request<SupplierReceipt[]>("/suppliers/receipts?limit=50", token),
      ]);
      setSuppliers(supplierList);
      setReceipts(receiptList);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to load suppliers");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  function resetSupplierForm() {
    setEditingId(null);
    setSupplierForm({
      name: "",
      contact_name: "",
      phone: "",
      email: "",
      address: "",
      is_active: true,
    });
  }

  function editSupplier(supplier: Supplier) {
    setError("");
    setNotice("");
    setEditingId(supplier.id);
    setSupplierForm({
      name: supplier.name,
      contact_name: supplier.contact_name || "",
      phone: supplier.phone || "",
      email: supplier.email || "",
      address: supplier.address || "",
      is_active: supplier.is_active,
    });
  }

  async function submitSupplier(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSavingSupplier(true);
    setError("");
    setNotice("");
    const payload = {
      name: supplierForm.name.trim(),
      contact_name: supplierForm.contact_name.trim() || null,
      phone: supplierForm.phone.trim() || null,
      email: supplierForm.email.trim() || null,
      address: supplierForm.address.trim() || null,
      ...(editingId !== null ? { is_active: supplierForm.is_active } : {}),
    };
    try {
      await request<Supplier>(
        editingId === null ? "/suppliers" : `/suppliers/${editingId}`,
        token,
        {
          method: editingId === null ? "POST" : "PATCH",
          body: JSON.stringify(payload),
        },
      );
      setNotice(editingId === null ? "Supplier added." : "Supplier updated.");
      resetSupplierForm();
      await loadData();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to save supplier");
    } finally {
      setSavingSupplier(false);
    }
  }

  async function submitReceipt(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (new Set(receiptLines.map((line) => line.product_id)).size !== receiptLines.length) {
      setError("Each product can only be listed once per delivery.");
      return;
    }
    setSavingReceipt(true);
    setError("");
    setNotice("");
    try {
      const receipt = await request<SupplierReceipt>("/suppliers/receipts", token, {
        method: "POST",
        body: JSON.stringify({
          supplier_id: Number(supplierId),
          supplier_reference: supplierReference.trim() || null,
          items: receiptLines.map((line) => ({
            product_id: Number(line.product_id),
            quantity_received: line.quantity_received,
          })),
        }),
      });
      setNotice(`Delivery #${receipt.id} recorded; stock updated.`);
      setSupplierReference("");
      setReceiptLines([{ product_id: "", quantity_received: "" }]);
      await Promise.all([loadData(), onProductsChanged()]);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to record delivery");
    } finally {
      setSavingReceipt(false);
    }
  }

  const activeSuppliers = suppliers.filter((supplier) => supplier.is_active);

  return (
    <section className="staff-page">
      <div className="page-heading staff-page-heading">
        <div>
          <span className="eyebrow">SUPPLIERS &amp; STOCK RECEIVING</span>
          <h1>Suppliers</h1>
          <p className="muted">Manage depot contacts and record deliveries into inventory.</p>
        </div>
        <button className="secondary-button" onClick={onBack}><ArrowLeft size={16} /> Back to POS</button>
      </div>

      {error && <div className="alert error inventory-alert"><CircleAlert size={15} />{error}</div>}
      {notice && <div className="alert success inventory-alert"><BadgeCheck size={15} />{notice}</div>}

      <div className="inventory-layout">
        <div className="inventory-side">
          <section className="staff-card">
            <div className="staff-card-heading">
              <div><h2>Supplier directory</h2><p>{suppliers.length} suppliers</p></div>
              <Truck size={19} />
            </div>
            {loading ? (
              <div className="staff-loading"><LoaderCircle className="spin" size={18} /> Loading suppliers...</div>
            ) : suppliers.length === 0 ? (
              <div className="staff-empty">Add your first supplier using the form.</div>
            ) : (
              <div className="staff-table-wrap">
                <table className="staff-table">
                  <thead><tr><th>Supplier</th><th>Contact</th><th>Status</th><th>Actions</th></tr></thead>
                  <tbody>
                    {suppliers.map((supplier) => (
                      <tr key={supplier.id}>
                        <td><b>{supplier.name}</b>{supplier.phone && <small>{supplier.phone}</small>}</td>
                        <td>{supplier.contact_name || supplier.email || "—"}</td>
                        <td><span className={`status-badge ${supplier.is_active ? "active" : "inactive"}`}>{supplier.is_active ? "Active" : "Inactive"}</span></td>
                        <td><button type="button" className="staff-action" onClick={() => editSupplier(supplier)} aria-label={`Edit ${supplier.name}`} title="Edit supplier"><Pencil size={15} /></button></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className="staff-card">
            <div className="staff-card-heading">
              <div><h2>Recent deliveries</h2><p>Most recent 50 supplier receipts</p></div>
              <ReceiptText size={19} />
            </div>
            {loading ? (
              <div className="staff-loading"><LoaderCircle className="spin" size={18} /> Loading deliveries...</div>
            ) : receipts.length === 0 ? (
              <div className="staff-empty">No supplier deliveries recorded yet.</div>
            ) : (
              <div className="staff-table-wrap">
                <table className="staff-table supplier-receipts-table">
                  <thead><tr><th>Received</th><th>Supplier / reference</th><th>Items</th></tr></thead>
                  <tbody>
                    {receipts.map((receipt) => (
                      <tr key={receipt.id}>
                        <td>{formatReceiptDate(receipt.received_at)}<small>By {receipt.received_by_name}</small></td>
                        <td><b>{receipt.supplier_name}</b><small>{receipt.supplier_reference || `Receipt #${receipt.id}`}</small></td>
                        <td>{receipt.items.map((item) => `${item.product_name} × ${item.quantity_received}`).join(", ")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>

        <div className="inventory-side">
          <form className="staff-card staff-form" onSubmit={submitSupplier}>
            <div className="staff-card-heading">
              <div><h2>{editingId === null ? "Add supplier" : "Edit supplier"}</h2><p>Keep depot contact details for receiving stock.</p></div>
              <Truck size={19} />
            </div>
            <label>Supplier name<input value={supplierForm.name} onChange={(event) => setSupplierForm({ ...supplierForm, name: event.target.value })} maxLength={160} required /></label>
            <label>Contact name <span className="optional-label">Optional</span><input value={supplierForm.contact_name} onChange={(event) => setSupplierForm({ ...supplierForm, contact_name: event.target.value })} maxLength={120} /></label>
            <label>Phone <span className="optional-label">Optional</span><input type="tel" value={supplierForm.phone} onChange={(event) => setSupplierForm({ ...supplierForm, phone: event.target.value })} maxLength={32} /></label>
            <label>Email <span className="optional-label">Optional</span><input type="email" value={supplierForm.email} onChange={(event) => setSupplierForm({ ...supplierForm, email: event.target.value })} maxLength={254} /></label>
            <label>Address <span className="optional-label">Optional</span><input value={supplierForm.address} onChange={(event) => setSupplierForm({ ...supplierForm, address: event.target.value })} maxLength={255} /></label>
            {editingId !== null && <label>Supplier status<select value={supplierForm.is_active ? "active" : "inactive"} onChange={(event) => setSupplierForm({ ...supplierForm, is_active: event.target.value === "active" })}><option value="active">Active</option><option value="inactive">Inactive</option></select></label>}
            <div className="staff-form-actions">
              {editingId !== null && <button type="button" className="secondary-button" onClick={resetSupplierForm}>Cancel</button>}
              <button type="submit" className="primary-button" disabled={savingSupplier}>{savingSupplier ? <LoaderCircle className="spin" size={17} /> : editingId === null ? "Add supplier" : "Save changes"}</button>
            </div>
          </form>

          <form className="staff-card staff-form" onSubmit={submitReceipt}>
            <div className="staff-card-heading">
              <div><h2>Record delivery</h2><p>Received quantities are added to stock.</p></div>
              <Package size={19} />
            </div>
            <label>Supplier<select value={supplierId} onChange={(event) => setSupplierId(event.target.value)} required>
              <option value="">Select a supplier</option>
              {activeSuppliers.map((supplier) => <option value={supplier.id} key={supplier.id}>{supplier.name}</option>)}
            </select></label>
            <label>Invoice / delivery reference <span className="optional-label">Optional</span><input value={supplierReference} onChange={(event) => setSupplierReference(event.target.value)} maxLength={80} /></label>
            <div className="supplier-lines">
              {receiptLines.map((line, index) => (
                <div className="supplier-line" key={index}>
                  <label>Product<select value={line.product_id} onChange={(event) => setReceiptLines((current) => current.map((item, lineIndex) => lineIndex === index ? { ...item, product_id: event.target.value } : item))} required>
                    <option value="">Select product</option>
                    {products.filter((product) => !receiptLines.some((other, otherIndex) => otherIndex !== index && other.product_id === String(product.id))).map((product) => <option value={product.id} key={product.id}>{product.name} · {product.stock_quantity} in stock</option>)}
                  </select></label>
                  <label>Qty received<input type="number" min="0.001" step="0.001" value={line.quantity_received} onChange={(event) => setReceiptLines((current) => current.map((item, lineIndex) => lineIndex === index ? { ...item, quantity_received: event.target.value } : item))} required /></label>
                  {receiptLines.length > 1 && <button type="button" className="remove-supplier-line" aria-label="Remove delivery item" onClick={() => setReceiptLines((current) => current.filter((_, lineIndex) => lineIndex !== index))}><X size={15} /></button>}
                </div>
              ))}
            </div>
            <button type="button" className="secondary-button supplier-add-line" onClick={() => setReceiptLines((current) => [...current, { product_id: "", quantity_received: "" }])} disabled={receiptLines.length >= products.length || products.length === 0}><Plus size={15} /> Add product</button>
            {products.length === 0 && <small className="field-hint">Add products before recording a delivery.</small>}
            <button type="submit" className="primary-button" disabled={savingReceipt || activeSuppliers.length === 0 || products.length === 0}>{savingReceipt ? <LoaderCircle className="spin" size={17} /> : "Record delivery & update stock"}</button>
          </form>
        </div>
      </div>
    </section>
  );
}

function WholesaleManagement({
  token,
  staffRole,
  products,
  onProductsChanged,
  onBack,
  onPrintInvoice,
}: {
  token: string;
  staffRole: Staff["role"];
  products: Product[];
  onProductsChanged: () => Promise<void>;
  onBack: () => void;
  onPrintInvoice: (sale: WholesaleSale) => void;
}) {
  const [customers, setCustomers] = useState<WholesaleCustomer[]>([]);
  const [sales, setSales] = useState<WholesaleSale[]>([]);
  const [customerForm, setCustomerForm] = useState({
    name: "",
    contact_name: "",
    phone: "",
    email: "",
    address: "",
    is_active: true,
  });
  const [editingCustomerId, setEditingCustomerId] = useState<number | null>(null);
  const [customerId, setCustomerId] = useState("");
  const [deliveryReference, setDeliveryReference] = useState("");
  const [lines, setLines] = useState([{ product_id: "", quantity: "", unit_price: "" }]);
  const [cashPayment, setCashPayment] = useState("");
  const [cashReceived, setCashReceived] = useState("");
  const [mpesaPayment, setMpesaPayment] = useState("");
  const [mpesaReference, setMpesaReference] = useState("");
  const [paymentSaleId, setPaymentSaleId] = useState<number | null>(null);
  const [paymentMethod, setPaymentMethod] = useState<"cash" | "mpesa">("cash");
  const [paymentAmount, setPaymentAmount] = useState("");
  const [paymentCashReceived, setPaymentCashReceived] = useState("");
  const [paymentMpesaReference, setPaymentMpesaReference] = useState("");
  const [loading, setLoading] = useState(true);
  const [savingCustomer, setSavingCustomer] = useState(false);
  const [savingSale, setSavingSale] = useState(false);
  const [savingPayment, setSavingPayment] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const loadData = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [customerList, saleList] = await Promise.all([
        request<WholesaleCustomer[]>("/wholesale/customers?active_only=false", token),
        request<WholesaleSale[]>("/wholesale/sales?limit=100", token),
      ]);
      setCustomers(customerList);
      setSales(saleList);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to load wholesale records");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  function resetCustomerForm() {
    setEditingCustomerId(null);
    setCustomerForm({
      name: "",
      contact_name: "",
      phone: "",
      email: "",
      address: "",
      is_active: true,
    });
  }

  function editCustomer(customer: WholesaleCustomer) {
    setEditingCustomerId(customer.id);
    setCustomerForm({
      name: customer.name,
      contact_name: customer.contact_name || "",
      phone: customer.phone || "",
      email: customer.email || "",
      address: customer.address || "",
      is_active: customer.is_active,
    });
    setError("");
    setNotice("");
  }

  async function submitCustomer(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSavingCustomer(true);
    setError("");
    setNotice("");
    const payload = {
      name: customerForm.name.trim(),
      contact_name: customerForm.contact_name.trim() || null,
      phone: customerForm.phone.trim() || null,
      email: customerForm.email.trim() || null,
      address: customerForm.address.trim() || null,
      ...(editingCustomerId !== null ? { is_active: customerForm.is_active } : {}),
    };
    try {
      await request<WholesaleCustomer>(
        editingCustomerId === null
          ? "/wholesale/customers"
          : `/wholesale/customers/${editingCustomerId}`,
        token,
        {
          method: editingCustomerId === null ? "POST" : "PATCH",
          body: JSON.stringify(payload),
        },
      );
      setNotice(editingCustomerId === null ? "Shop added." : "Shop updated.");
      resetCustomerForm();
      await loadData();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to save shop");
    } finally {
      setSavingCustomer(false);
    }
  }

  function updateLine(index: number, key: "product_id" | "quantity" | "unit_price", value: string) {
    setLines((current) => current.map((line, lineIndex) => {
      if (lineIndex !== index) return line;
      if (key === "product_id") {
        const product = products.find((item) => item.id === Number(value));
        return {
          ...line,
          product_id: value,
          unit_price: product?.unit_price || "",
        };
      }
      return { ...line, [key]: value };
    }));
  }

  const deliveryTotal = lines.reduce(
    (sum, line) => sum + Number(line.quantity || 0) * Number(line.unit_price || 0),
    0,
  );
  const initialPaymentTotal = Number(cashPayment || 0) + Number(mpesaPayment || 0);

  async function submitWholesaleSale(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (new Set(lines.map((line) => line.product_id)).size !== lines.length) {
      setError("Each product can only be listed once per delivery.");
      return;
    }
    if (initialPaymentTotal > deliveryTotal) {
      setError("Payments cannot exceed the delivery total.");
      return;
    }
    if (Number(cashPayment) > 0 && Number(cashReceived || cashPayment) < Number(cashPayment)) {
      setError("Cash received must cover the cash payment.");
      return;
    }
    setSavingSale(true);
    setError("");
    setNotice("");
    const payments = [];
    if (Number(cashPayment) > 0) {
      payments.push({
        method: "cash",
        amount: Number(cashPayment).toFixed(2),
        cash_received: Number(cashReceived || cashPayment).toFixed(2),
      });
    }
    if (Number(mpesaPayment) > 0) {
      payments.push({
        method: "mpesa",
        amount: Number(mpesaPayment).toFixed(2),
        ...(mpesaReference.trim() ? { mpesa_reference: mpesaReference.trim() } : {}),
      });
    }
    try {
      const sale = await request<WholesaleSale>("/wholesale/sales", token, {
        method: "POST",
        body: JSON.stringify({
          customer_id: Number(customerId),
          delivery_reference: deliveryReference.trim() || null,
          items: lines.map((line) => ({
            product_id: Number(line.product_id),
            quantity: line.quantity,
            unit_price: line.unit_price,
          })),
          payments,
        }),
      });
      setNotice(`Delivery #${sale.id} recorded; stock updated.`);
      setDeliveryReference("");
      setLines([{ product_id: "", quantity: "", unit_price: "" }]);
      setCashPayment("");
      setCashReceived("");
      setMpesaPayment("");
      setMpesaReference("");
      onPrintInvoice(sale);
      await loadData();
      try {
        await onProductsChanged();
      } catch {
        setError("Delivery recorded, but the product stock display could not be refreshed.");
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to record delivery");
    } finally {
      setSavingSale(false);
    }
  }

  async function submitPayment(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!paymentSaleId) return;
    const amount = Number(paymentAmount);
    if (paymentMethod === "cash" && Number(paymentCashReceived || paymentAmount) < amount) {
      setError("Cash received must cover the payment.");
      return;
    }
    setSavingPayment(true);
    setError("");
    setNotice("");
    try {
      await request<WholesaleSale>(`/wholesale/sales/${paymentSaleId}/payments`, token, {
        method: "POST",
        body: JSON.stringify({
          method: paymentMethod,
          amount: paymentAmount,
          ...(paymentMethod === "cash"
            ? { cash_received: paymentCashReceived || paymentAmount }
            : paymentMpesaReference.trim()
              ? { mpesa_reference: paymentMpesaReference.trim() }
              : {}),
        }),
      });
      setNotice(`Payment recorded against delivery #${paymentSaleId}.`);
      setPaymentSaleId(null);
      setPaymentAmount("");
      setPaymentCashReceived("");
      setPaymentMpesaReference("");
      await loadData();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to record payment");
    } finally {
      setSavingPayment(false);
    }
  }

  const activeCustomers = customers.filter((customer) => customer.is_active);

  return (
    <section className="staff-page">
      <div className="page-heading staff-page-heading">
        <div>
          <span className="eyebrow">WHOLESALE &amp; SHOP ACCOUNTS</span>
          <h1>Wholesale deliveries</h1>
          <p className="muted">Deliver stock to shops, record payments, and track balances due.</p>
        </div>
        <button className="secondary-button" onClick={onBack}><ArrowLeft size={16} /> Back to POS</button>
      </div>
      {error && <div className="alert error inventory-alert"><CircleAlert size={15} />{error}</div>}
      {notice && <div className="alert success inventory-alert"><BadgeCheck size={15} />{notice}</div>}

      <div className="inventory-layout">
        <div className="inventory-side">
          <section className="staff-card">
            <div className="staff-card-heading">
              <div><h2>Shop customers</h2><p>{customers.length} shops</p></div>
              <Users size={19} />
            </div>
            {loading ? (
              <div className="staff-loading"><LoaderCircle className="spin" size={18} /> Loading shops...</div>
            ) : customers.length === 0 ? (
              <div className="staff-empty">Add a shop customer to start recording wholesale deliveries.</div>
            ) : (
              <div className="staff-table-wrap">
                <table className="staff-table">
                  <thead><tr><th>Shop</th><th>Contact</th><th>Status</th>{staffRole === "admin" && <th>Actions</th>}</tr></thead>
                  <tbody>
                    {customers.map((customer) => (
                      <tr key={customer.id}>
                        <td><b>{customer.name}</b>{customer.phone && <small>{customer.phone}</small>}</td>
                        <td>{customer.contact_name || customer.email || "—"}</td>
                        <td><span className={`status-badge ${customer.is_active ? "active" : "inactive"}`}>{customer.is_active ? "Active" : "Inactive"}</span></td>
                        {staffRole === "admin" && <td><button type="button" className="staff-action" onClick={() => editCustomer(customer)} aria-label={`Edit ${customer.name}`} title="Edit shop"><Pencil size={15} /></button></td>}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className="staff-card">
            <div className="staff-card-heading">
              <div><h2>Wholesale account activity</h2><p>Most recent 100 deliveries</p></div>
              <ReceiptText size={19} />
            </div>
            {loading ? (
              <div className="staff-loading"><LoaderCircle className="spin" size={18} /> Loading deliveries...</div>
            ) : sales.length === 0 ? (
              <div className="staff-empty">No wholesale deliveries recorded yet.</div>
            ) : (
              <div className="staff-table-wrap">
                <table className="staff-table wholesale-table">
                  <thead><tr><th>Date / shop</th><th>Total</th><th>Paid / balance</th><th>Status</th><th>Actions</th></tr></thead>
                  <tbody>
                    {sales.map((sale) => (
                      <Fragment key={sale.id}>
                        <tr>
                          <td><b>{sale.customer_name}</b><small>#{sale.id} · {formatReceiptDate(sale.created_at)}{sale.delivery_reference ? ` · ${sale.delivery_reference}` : ""}</small></td>
                          <td>{money(sale.total)}</td>
                          <td><b>{money(sale.amount_paid)} paid</b><small>{money(sale.balance_due)} due</small></td>
                          <td><span className={`status-badge ${sale.payment_status === "paid" ? "active" : "inactive"}`}>{sale.payment_status}</span></td>
                          <td><button type="button" className="staff-action" onClick={() => onPrintInvoice(sale)} aria-label={`Print invoice ${sale.id}`} title="View/print invoice"><Printer size={15} /></button></td>
                        </tr>
                        {sale.balance_due !== "0.00" && sale.payment_status !== "paid" && (
                          <tr className="wholesale-detail-row">
                            <td colSpan={5}>
                              {paymentSaleId === sale.id ? (
                                <form className="wholesale-payment-form" onSubmit={submitPayment}>
                                  <label>Method<select value={paymentMethod} onChange={(event) => setPaymentMethod(event.target.value as "cash" | "mpesa")}><option value="cash">Cash</option><option value="mpesa">M-Pesa</option></select></label>
                                  <label>Amount<input type="number" min="0.01" max={sale.balance_due} step="0.01" value={paymentAmount} onChange={(event) => setPaymentAmount(event.target.value)} required /></label>
                                  {paymentMethod === "cash"
                                    ? <label>Cash received<input type="number" min={paymentAmount || "0.01"} step="0.01" value={paymentCashReceived} onChange={(event) => setPaymentCashReceived(event.target.value)} /></label>
                                    : <label>M-Pesa reference<input value={paymentMpesaReference} onChange={(event) => setPaymentMpesaReference(event.target.value)} maxLength={64} /></label>}
                                  <div className="wholesale-payment-actions">
                                    <button type="button" className="secondary-button" onClick={() => setPaymentSaleId(null)}>Cancel</button>
                                    <button type="submit" className="primary-button" disabled={savingPayment}>{savingPayment ? <LoaderCircle className="spin" size={16} /> : "Save payment"}</button>
                                  </div>
                                </form>
                              ) : (
                                <div className="wholesale-detail-content">
                                  <div><b>Items</b>{sale.items.map((item) => <p key={item.id}>{item.product_name} · {item.quantity} × {money(item.unit_price)} <span>{money(item.line_total)}</span></p>)}</div>
                                  <div><b>Payments</b>{sale.payments.length ? sale.payments.map((payment) => <p key={payment.id}>{payment.method === "mpesa" ? "M-Pesa" : "Cash"} <span>{money(payment.amount)}</span>{payment.mpesa_reference && <small> · Ref {payment.mpesa_reference}</small>}</p>) : <p>No payments recorded yet.</p>}</div>
                                  <button type="button" className="secondary-button" onClick={() => { setPaymentSaleId(sale.id); setPaymentAmount(sale.balance_due); }}>Add payment · {money(sale.balance_due)} due</button>
                                </div>
                              )}
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>

        <div className="inventory-side">
          {staffRole === "admin" && (
            <form className="staff-card staff-form" onSubmit={submitCustomer}>
              <div className="staff-card-heading">
                <div><h2>{editingCustomerId === null ? "Add shop customer" : "Edit shop customer"}</h2><p>Contact details for your wholesale account.</p></div>
                <Users size={19} />
              </div>
              <label>Shop name<input value={customerForm.name} onChange={(event) => setCustomerForm({ ...customerForm, name: event.target.value })} maxLength={160} required /></label>
              <label>Contact name <span className="optional-label">Optional</span><input value={customerForm.contact_name} onChange={(event) => setCustomerForm({ ...customerForm, contact_name: event.target.value })} maxLength={120} /></label>
              <label>Phone <span className="optional-label">Optional</span><input type="tel" value={customerForm.phone} onChange={(event) => setCustomerForm({ ...customerForm, phone: event.target.value })} maxLength={32} /></label>
              <label>Email <span className="optional-label">Optional</span><input type="email" value={customerForm.email} onChange={(event) => setCustomerForm({ ...customerForm, email: event.target.value })} maxLength={254} /></label>
              <label>Address <span className="optional-label">Optional</span><input value={customerForm.address} onChange={(event) => setCustomerForm({ ...customerForm, address: event.target.value })} maxLength={255} /></label>
              {editingCustomerId !== null && <label>Shop status<select value={customerForm.is_active ? "active" : "inactive"} onChange={(event) => setCustomerForm({ ...customerForm, is_active: event.target.value === "active" })}><option value="active">Active</option><option value="inactive">Inactive</option></select></label>}
              <div className="staff-form-actions">
                {editingCustomerId !== null && <button type="button" className="secondary-button" onClick={resetCustomerForm}>Cancel</button>}
                <button type="submit" className="primary-button" disabled={savingCustomer}>{savingCustomer ? <LoaderCircle className="spin" size={17} /> : editingCustomerId === null ? "Add shop" : "Save changes"}</button>
              </div>
            </form>
          )}

          <form className="staff-card staff-form" onSubmit={submitWholesaleSale}>
            <div className="staff-card-heading">
              <div><h2>New wholesale delivery</h2><p>Enter the agreed price for this delivery.</p></div>
              <Truck size={19} />
            </div>
            <label>Shop customer<select value={customerId} onChange={(event) => setCustomerId(event.target.value)} required>
              <option value="">Select a shop</option>
              {activeCustomers.map((customer) => <option value={customer.id} key={customer.id}>{customer.name}</option>)}
            </select></label>
            <label>Delivery reference <span className="optional-label">Optional</span><input value={deliveryReference} onChange={(event) => setDeliveryReference(event.target.value)} maxLength={80} /></label>
            <div className="supplier-lines">
              {lines.map((line, index) => (
                <div className="wholesale-line" key={index}>
                  <label>Product<select value={line.product_id} onChange={(event) => updateLine(index, "product_id", event.target.value)} required>
                    <option value="">Select product</option>
                    {products.filter((product) => product.is_active && Number(product.stock_quantity) > 0 && !lines.some((other, otherIndex) => otherIndex !== index && other.product_id === String(product.id))).map((product) => <option value={product.id} key={product.id}>{product.name} · {product.stock_quantity} in stock</option>)}
                  </select></label>
                  <div className="wholesale-line-fields">
                    <label>Qty<input type="number" min="0.001" max={products.find((product) => product.id === Number(line.product_id))?.stock_quantity} step="0.001" value={line.quantity} onChange={(event) => updateLine(index, "quantity", event.target.value)} required /></label>
                    <label>Unit price<input type="number" min="0" step="0.01" value={line.unit_price} onChange={(event) => updateLine(index, "unit_price", event.target.value)} required /></label>
                  </div>
                  {lines.length > 1 && <button type="button" className="remove-supplier-line" aria-label="Remove wholesale item" onClick={() => setLines((current) => current.filter((_, lineIndex) => lineIndex !== index))}><X size={15} /></button>}
                </div>
              ))}
            </div>
            <button type="button" className="secondary-button supplier-add-line" onClick={() => setLines((current) => [...current, { product_id: "", quantity: "", unit_price: "" }])} disabled={lines.length >= products.filter((product) => product.is_active && Number(product.stock_quantity) > 0).length}><Plus size={15} /> Add product</button>
            <div className="wholesale-total"><span>Delivery total</span><b>{money(deliveryTotal)}</b></div>
            <div className="wholesale-payment-inputs">
              <label>Cash paid now<input type="number" min="0" max={deliveryTotal} step="0.01" value={cashPayment} onChange={(event) => setCashPayment(event.target.value)} /></label>
              <label>Cash received<input type="number" min={cashPayment || "0"} step="0.01" value={cashReceived} onChange={(event) => setCashReceived(event.target.value)} placeholder={cashPayment || "0.00"} /></label>
              <label>M-Pesa paid now<input type="number" min="0" max={deliveryTotal} step="0.01" value={mpesaPayment} onChange={(event) => setMpesaPayment(event.target.value)} /></label>
              <label>M-Pesa reference<input value={mpesaReference} onChange={(event) => setMpesaReference(event.target.value)} maxLength={64} /></label>
            </div>
            <small className="field-hint">Leave payments at zero for credit, or record full/partial cash and M-Pesa payments.</small>
            {initialPaymentTotal > deliveryTotal && <div className="alert error">Payments exceed the delivery total.</div>}
            <button type="submit" className="primary-button" disabled={savingSale || activeCustomers.length === 0 || products.length === 0}>{savingSale ? <LoaderCircle className="spin" size={17} /> : "Record delivery & print invoice"}</button>
          </form>
        </div>
      </div>
    </section>
  );
}

function SalesHistory({
  token,
  onBack,
}: {
  token: string;
  onBack: () => void;
}) {
  const [saleDate, setSaleDate] = useState(() => localDateValue(new Date()));
  const [period, setPeriod] = useState<SalesSummary["period"]>("daily");
  const [summary, setSummary] = useState<SalesSummary | null>(null);
  const [sales, setSales] = useState<Sale[]>([]);
  const [offset, setOffset] = useState(0);
  const [expandedSaleId, setExpandedSaleId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const pageSize = 50;

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    const [fromDate, toDate] = reportDateRange(saleDate, period);
    Promise.all([
      request<SalesSummary>(`/sales/summary?period=${period}&date=${saleDate}`, token),
      request<Sale[]>(`/sales?from_date=${fromDate}&to_date=${toDate}&offset=${offset}&limit=${pageSize}`, token),
    ])
      .then(([dailySummary, dailySales]) => {
        if (!active) return;
        setSummary(dailySummary);
        setSales(dailySales);
      })
      .catch((caught) => {
        if (!active) return;
        setError(caught instanceof Error ? caught.message : "Unable to load sales");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [offset, period, saleDate, token]);

  function changeDate(value: string) {
    setSaleDate(value);
    setOffset(0);
    setExpandedSaleId(null);
  }

  function changePeriod(value: SalesSummary["period"]) {
    setPeriod(value);
    setOffset(0);
    setExpandedSaleId(null);
  }

  const periodLabel = period === "daily" ? "Daily" : period === "weekly" ? "Weekly" : "Monthly";

  return (
    <section className="staff-page">
      <div className="page-heading staff-page-heading">
        <div>
          <span className="eyebrow">SALES &amp; REPORTS</span>
          <h1>Sales history</h1>
          <p className="muted">Review transactions and cumulative payment totals.</p>
        </div>
        <div className="sales-heading-actions">
          <div className="sales-period-picker" aria-label="Report period">
            {(["daily", "weekly", "monthly"] as const).map((value) => (
              <button key={value} className={period === value ? "selected" : ""} onClick={() => changePeriod(value)}>{value}</button>
            ))}
          </div>
          <label className="sales-date-picker"><CalendarDays size={16} /><span>{period === "daily" ? "Date" : "Anchor date"}</span><input type="date" value={saleDate} onChange={(event) => changeDate(event.target.value)} required /></label>
          <button className="secondary-button" onClick={onBack}><ArrowLeft size={16} /> Back to POS</button>
        </div>
      </div>

      {error && <div className="alert error inventory-alert"><CircleAlert size={15} />{error}</div>}

      <div className="sales-summary-grid">
        <article className="sales-summary-card"><span>{periodLabel} sales</span><strong>{loading ? "—" : summary?.sale_count ?? 0}</strong><small>transactions in this period</small></article>
        <article className="sales-summary-card"><span>Sales total</span><strong>{loading ? "—" : money(summary?.total || 0)}</strong><small>total value of completed sales</small></article>
        <article className="sales-summary-card"><span>Cash</span><strong>{loading ? "—" : money(summary?.cash_total || 0)}</strong><small>cash payment allocations</small></article>
        <article className="sales-summary-card"><span>M-Pesa</span><strong>{loading ? "—" : money(summary?.mpesa_total || 0)}</strong><small>M-Pesa payment allocations</small></article>
      </div>

      <section className="staff-card sales-history-card">
        <div className="staff-card-heading">
          <div><h2>Transactions</h2><p>{summary ? `${summary.start_date} – ${summary.end_date} · East Africa Time` : `${periodLabel} · East Africa Time`}</p></div>
          <ReceiptText size={19} />
        </div>
        {loading ? (
          <div className="staff-loading"><LoaderCircle className="spin" size={18} /> Loading transactions...</div>
        ) : sales.length === 0 ? (
          <div className="staff-empty">No sales recorded on this date.</div>
        ) : (
          <>
            <div className="staff-table-wrap">
              <table className="staff-table sales-table">
                <thead><tr><th>Sale</th><th>Time</th><th>Items</th><th>Payment</th><th>Total</th><th>Details</th></tr></thead>
                <tbody>
                  {sales.map((sale) => (
                    <Fragment key={sale.id}>
                      <tr>
                        <td><b>#{sale.id}</b></td>
                        <td>{formatSaleTime(sale.created_at)}</td>
                        <td>{sale.items.reduce((quantity, item) => quantity + Number(item.quantity), 0)}</td>
                        <td><div className="sale-methods">{sale.payments.map((payment) => <span className={`payment-badge ${payment.method}`} key={payment.id}>{payment.method === "mpesa" ? "M-Pesa" : "Cash"}</span>)}</div></td>
                        <td><b>{money(sale.total)}</b></td>
                        <td><button className="secondary-button sale-details-button" onClick={() => setExpandedSaleId(expandedSaleId === sale.id ? null : sale.id)}>{expandedSaleId === sale.id ? "Hide" : "View"}</button></td>
                      </tr>
                      {expandedSaleId === sale.id && (
                        <tr className="sale-detail-row" key={`${sale.id}-details`}>
                          <td colSpan={6}>
                            <div className="sale-detail-content">
                              <div><b>Items</b>{sale.items.map((item) => <p key={item.id}>{item.product_name} · {item.quantity} × {money(item.unit_price)} <span>{money(item.line_total)}</span></p>)}</div>
                              <div><b>Payments</b>{sale.payments.map((payment) => <p key={payment.id}>{payment.method === "mpesa" ? "M-Pesa" : "Cash"} <span>{money(payment.amount)}</span>{payment.change_given !== "0.00" && <small> · Change {money(payment.change_given)}</small>}{payment.mpesa_reference && <small> · Ref {payment.mpesa_reference}</small>}</p>)}</div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="sales-pagination">
              <span>Showing {offset + 1}–{offset + sales.length} transactions</span>
              <div>
                <button className="secondary-button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - pageSize))}><ChevronLeft size={15} /> Previous</button>
                <button className="secondary-button" disabled={sales.length < pageSize} onClick={() => setOffset(offset + pageSize)}>Next <ChevronRight size={15} /></button>
              </div>
            </div>
          </>
        )}
      </section>
    </section>
  );
}

export default function App() {
  const [token, setToken] = useState(() => sessionStorage.getItem("urban-pos-token") || "");
  const [staff, setStaff] = useState<Staff | null>(null);
  const [activePage, setActivePage] = useState<"pos" | "staff" | "inventory" | "sales" | "suppliers" | "wholesale">("pos");
  const [products, setProducts] = useState<Product[]>([]);
  const [cart, setCart] = useState<CartLine[]>([]);
  const [completedSale, setCompletedSale] = useState<Sale | null>(null);
  const [completedWholesaleSale, setCompletedWholesaleSale] = useState<WholesaleSale | null>(null);
  const [search, setSearch] = useState("");
  const [paymentMethod, setPaymentMethod] = useState<"cash" | "mpesa" | "split">("cash");
  const [cashAllocation, setCashAllocation] = useState("");
  const [cashReceived, setCashReceived] = useState("");
  const [mpesaReference, setMpesaReference] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const logout = useCallback(() => {
    sessionStorage.removeItem("urban-pos-token");
    setToken("");
    setStaff(null);
    setProducts([]);
    setCart([]);
    setCompletedSale(null);
    setCompletedWholesaleSale(null);
    setNotice("");
    setActivePage("pos");
  }, []);

  const refreshProducts = useCallback(async (activeToken: string) => {
    const items = await request<Product[]>("/inventory/products?limit=200", activeToken);
    setProducts(items);
  }, []);

  useEffect(() => {
    if (!token) return;
    let active = true;
    Promise.all([
      request<Staff>("/auth/me", token),
      request<Product[]>("/inventory/products?limit=200", token),
    ])
      .then(([currentStaff, items]) => {
        if (!active) return;
        setStaff(currentStaff);
        setProducts(items);
      })
      .catch(() => {
        if (active) logout();
      });
    return () => {
      active = false;
    };
  }, [token, logout]);

  const filteredProducts = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return products;
    return products.filter((product) =>
      [product.name, product.barcode || ""].some((value) =>
        value.toLowerCase().includes(query),
      ),
    );
  }, [products, search]);

  const lowStockProducts = useMemo(
    () => products.filter(
      (product) => Number(product.stock_quantity) <= Number(product.low_stock_threshold),
    ),
    [products],
  );

  const total = cart.reduce(
    (sum, line) => sum + Number(line.product.unit_price) * line.quantity,
    0,
  );
  const cashAmount = paymentMethod === "cash"
    ? total
    : paymentMethod === "split"
      ? Math.min(total, Math.max(0, Number(cashAllocation) || 0))
      : 0;
  const mpesaAmount = total - cashAmount;
  const cashChange = Math.max(0, (Number(cashReceived) || 0) - cashAmount);

  function addToCart(product: Product) {
    if (Number(product.stock_quantity) <= 0) return;
    setCart((current) => {
      const line = current.find((item) => item.product.id === product.id);
      if (!line) return [...current, { product, quantity: 1 }];
      if (line.quantity >= Number(product.stock_quantity)) return current;
      return current.map((item) =>
        item.product.id === product.id ? { ...item, quantity: item.quantity + 1 } : item,
      );
    });
  }

  function changeQuantity(productId: number, delta: number) {
    setCart((current) =>
      current
        .map((line) => {
          if (line.product.id !== productId) return line;
          const quantity = Math.min(
            Number(line.product.stock_quantity),
            line.quantity + delta,
          );
          return { ...line, quantity };
        })
        .filter((line) => line.quantity > 0),
    );
  }

  async function submitLogin(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const form = new FormData(event.currentTarget);
    try {
      const response = await fetch(`${API_URL}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: form.get("username"),
          password: form.get("password"),
        }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body?.detail || "Unable to sign in");
      sessionStorage.setItem("urban-pos-token", body.access_token);
      setStaff(body.staff);
      setToken(body.access_token);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to sign in");
    } finally {
      setBusy(false);
    }
  }

  async function completeSale() {
    if (!token || !cart.length || total <= 0) return;
    if (paymentMethod === "split" && (cashAmount <= 0 || mpesaAmount <= 0)) {
      setError("Enter a cash amount between zero and the sale total to split payment.");
      return;
    }
    if (cashAmount > 0 && (Number(cashReceived) || 0) < cashAmount) {
      setError("Cash received must cover the cash portion.");
      return;
    }

    const payments = [];
    if (cashAmount > 0) {
      payments.push({
        method: "cash",
        amount: cashAmount.toFixed(2),
        cash_received: Number(cashReceived || cashAmount).toFixed(2),
      });
    }
    if (mpesaAmount > 0) {
      payments.push({
        method: "mpesa",
        amount: mpesaAmount.toFixed(2),
        ...(mpesaReference.trim() ? { mpesa_reference: mpesaReference.trim() } : {}),
      });
    }

    setBusy(true);
    setError("");
    setNotice("");
    try {
      const sale = await request<Sale>("/sales", token, {
        method: "POST",
        body: JSON.stringify({
          items: cart.map((line) => ({
            product_id: line.product.id,
            quantity: line.quantity,
          })),
          payments,
        }),
      });
      setNotice(`Sale #${sale.id} completed successfully.`);
      setCompletedSale(sale);
      setCart([]);
      setCashReceived("");
      setCashAllocation("");
      setMpesaReference("");
      await refreshProducts(token);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to complete sale");
    } finally {
      setBusy(false);
    }
  }

  if (!token || !staff) {
    return (
      <main className="login-shell">
        <section className="login-aside">
          <div className="brand brand-light"><span className="brand-mark"><Wine size={20} /></span> URBAN LIQUOR LITEIN</div>
          <div className="aside-copy">
            <span className="eyebrow">STORE OPERATIONS</span>
            <h1>Good drinks.<br />Better business.</h1>
            <p>Your counter, inventory, and daily sales—together in one place.</p>
          </div>
          <div className="aside-foot"><ShieldCheck size={16} /> Staff access only</div>
        </section>
        <section className="login-panel">
          <div className="login-card">
            <div className="mobile-brand brand"><span className="brand-mark"><Wine size={20} /></span> URBAN LIQUOR LITEIN</div>
            <span className="eyebrow">WELCOME BACK</span>
            <h2>Sign in to your store</h2>
            <p className="muted">Use your staff account to open the point of sale.</p>
            <form onSubmit={submitLogin} className="login-form">
              <label htmlFor="username">Username</label>
              <input id="username" name="username" type="text" autoComplete="username" placeholder="e.g. storeadmin" minLength={3} maxLength={254} required />
              <label htmlFor="password">Password</label>
              <input id="password" name="password" type="password" autoComplete="current-password" placeholder="Enter your password" required />
              {error && <div className="alert error"><CircleAlert size={16} />{error}</div>}
              <button className="primary-button login-submit" disabled={busy}>
                {busy ? <LoaderCircle className="spin" size={18} /> : <>Sign in <ArrowRight size={17} /></>}
              </button>
            </form>
            <div className="login-note"><ShieldCheck size={16} /> Your account is managed by your store owner.</div>
          </div>
          <footer>Urban Liquor Litein POS <span>•</span> Secure staff sign-in</footer>
        </section>
      </main>
    );
  }

  return (
    <main className="pos-shell">
      <header className="topbar">
        <div className="brand"><span className="brand-mark"><Wine size={20} /></span> URBAN LIQUOR LITEIN</div>
        <div className="topbar-right">
          <button className={`top-nav-button ${activePage === "sales" ? "selected" : ""}`} onClick={() => setActivePage("sales")} aria-label="Sales" title="Sales"><ReceiptText size={16} /><span>Sales</span></button>
          <button className={`top-nav-button ${activePage === "wholesale" ? "selected" : ""}`} onClick={() => setActivePage("wholesale")} aria-label="Wholesale" title="Wholesale"><Truck size={16} /><span>Wholesale</span></button>
          {staff.role === "admin" && (
            <>
              <button className={`top-nav-button ${activePage === "inventory" ? "selected" : ""}`} onClick={() => setActivePage("inventory")} aria-label="Products" title="Products"><Package size={16} /><span>Products</span></button>
              <button className={`top-nav-button ${activePage === "suppliers" ? "selected" : ""}`} onClick={() => setActivePage("suppliers")} aria-label="Suppliers" title="Suppliers"><Truck size={16} /><span>Suppliers</span></button>
              <button className={`top-nav-button ${activePage === "staff" ? "selected" : ""}`} onClick={() => setActivePage("staff")} aria-label="Staff" title="Staff"><Users size={16} /><span>Staff</span></button>
            </>
          )}
          <div className="staff-chip"><span className="avatar">{staff.full_name.slice(0, 1).toUpperCase()}</span><span><b>{staff.full_name}</b><small>{staff.role}</small></span></div>
          <button className="icon-button" onClick={logout} aria-label="Sign out" title="Sign out"><LogOut size={18} /></button>
        </div>
      </header>
      {lowStockProducts.length > 0 && (
        <aside className="stock-alert" role="status" aria-live="polite">
          <CircleAlert size={21} aria-hidden="true" />
          <div className="stock-alert-content">
            <strong>
              Low stock: {lowStockProducts.length} product{lowStockProducts.length === 1 ? "" : "s"}
            </strong>
            <ul>
              {lowStockProducts.slice(0, 3).map((product) => (
                <li key={product.id}>
                  {product.name}: {product.stock_quantity} left (alert at {product.low_stock_threshold})
                </li>
              ))}
              {lowStockProducts.length > 3 && <li>And {lowStockProducts.length - 3} more</li>}
            </ul>
          </div>
        </aside>
      )}
      {staff.role === "admin" && activePage === "suppliers" ? (
        <SuppliersManagement
          token={token}
          products={products}
          onProductsChanged={() => refreshProducts(token)}
          onBack={() => setActivePage("pos")}
        />
      ) : activePage === "wholesale" ? (
        <WholesaleManagement
          token={token}
          staffRole={staff.role}
          products={products}
          onProductsChanged={() => refreshProducts(token)}
          onBack={() => setActivePage("pos")}
          onPrintInvoice={setCompletedWholesaleSale}
        />
      ) : staff.role === "admin" && activePage === "inventory" ? (
        <InventoryManagement
          token={token}
          onBack={() => setActivePage("pos")}
          onProductsChanged={() => refreshProducts(token)}
        />
      ) : activePage === "sales" ? (
        <SalesHistory token={token} onBack={() => setActivePage("pos")} />
      ) : staff.role === "admin" && activePage === "staff" ? (
        <StaffManagement token={token} currentStaff={staff} onBack={() => setActivePage("pos")} />
      ) : <section className="workspace">
        <div className="catalog">
          <div className="page-heading">
            <div><span className="eyebrow">POINT OF SALE</span><h1>Checkout</h1><p className="muted">Find a product or scan its barcode to add it to the sale.</p></div>
            <div className="product-count"><Wine size={17} /> {products.length} products</div>
          </div>
          <label className="search-box"><Search size={18} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search name or barcode..." /><kbd>⌕</kbd></label>
          <div className="product-grid">
            {filteredProducts.map((product) => {
              const stock = Number(product.stock_quantity);
              const low = stock <= Number(product.low_stock_threshold);
              return (
                <button className="product-card" key={product.id} onClick={() => addToCart(product)} disabled={stock <= 0}>
                  <div className="product-art"><Wine size={24} /><span>{product.category || "BOTTLE"}</span></div>
                  <div className="product-info"><b>{product.name}</b><div className="product-meta"><strong>{money(product.unit_price)}</strong><span className={low ? "stock low" : "stock"}>{stock} in stock</span></div></div>
                  <span className="add-product"><Plus size={16} /></span>
                </button>
              );
            })}
            {!filteredProducts.length && <div className="empty-products"><ShoppingBag size={24} /><b>No products found</b><span>Try a different search, or ask your owner to add products.</span></div>}
          </div>
        </div>

        <aside className="cart-panel">
          <div className="cart-heading"><div><span className="eyebrow">CURRENT SALE</span><h2>Order summary</h2></div><span className="cart-count">{cart.reduce((sum, line) => sum + line.quantity, 0)}</span></div>
          <div className="cart-lines">
            {!cart.length ? <div className="empty-cart"><ShoppingBag size={26} /><b>Your sale is empty</b><span>Select products to start checkout.</span></div> : cart.map((line) => (
              <div className="cart-line" key={line.product.id}>
                <div className="line-icon"><Wine size={17} /></div>
                <div className="line-details"><b>{line.product.name}</b><span>{money(line.product.unit_price)} each</span></div>
                <div className="quantity-control"><button onClick={() => changeQuantity(line.product.id, -1)} aria-label="Decrease quantity"><Minus size={13} /></button><span>{line.quantity}</span><button onClick={() => changeQuantity(line.product.id, 1)} aria-label="Increase quantity"><Plus size={13} /></button></div>
                <strong className="line-total">{money(Number(line.product.unit_price) * line.quantity)}</strong>
                <button className="remove-line" aria-label="Remove item" onClick={() => setCart((current) => current.filter((entry) => entry.product.id !== line.product.id))}><X size={15} /></button>
              </div>
            ))}
          </div>
          <div className="checkout">
            <div className="total-row"><span>Total due</span><strong>{money(total)}</strong></div>
            <div className="payment-title"><span>PAYMENT METHOD</span><span>Split payment supported</span></div>
            <div className="payment-options">
              <button className={paymentMethod === "cash" ? "payment-option selected" : "payment-option"} onClick={() => setPaymentMethod("cash")}><Banknote size={17} />Cash</button>
              <button className={paymentMethod === "mpesa" ? "payment-option selected" : "payment-option"} onClick={() => setPaymentMethod("mpesa")}><Smartphone size={17} />M-Pesa</button>
              <button className={paymentMethod === "split" ? "payment-option selected" : "payment-option"} onClick={() => { setPaymentMethod("split"); setCashAllocation(total ? (total / 2).toFixed(2) : ""); }}><ArrowDownLeft size={17} />Split</button>
            </div>
            {(paymentMethod === "cash" || paymentMethod === "split") && (
              <div className="payment-fields">
                {paymentMethod === "split" && <label>Cash portion<input type="number" min="0.01" max={total} step="0.01" value={cashAllocation} onChange={(event) => setCashAllocation(event.target.value)} placeholder="Amount paid in cash" /></label>}
                <label>Cash received<input type="number" min={cashAmount} step="0.01" value={cashReceived} onChange={(event) => setCashReceived(event.target.value)} placeholder={money(cashAmount)} /></label>
                {cashChange > 0 && <div className="change-row">Change due <b>{money(cashChange)}</b></div>}
              </div>
            )}
            {(paymentMethod === "mpesa" || paymentMethod === "split") && <label className="reference-field">M-Pesa reference <input value={mpesaReference} onChange={(event) => setMpesaReference(event.target.value)} placeholder="Optional transaction code" /></label>}
            {error && <div className="alert error"><CircleAlert size={15} />{error}</div>}
            {notice && <div className="alert success"><BadgeCheck size={15} />{notice}</div>}
            <button className="primary-button complete-button" disabled={!cart.length || busy || (paymentMethod === "split" && (!cashAmount || !mpesaAmount))} onClick={completeSale}>
              {busy ? <LoaderCircle className="spin" size={18} /> : <><Check size={17} /> Complete sale <span>{money(total)}</span></>}
            </button>
            <p className="checkout-footnote"><ShieldCheck size={14} /> Stock updates when the sale is completed.</p>
          </div>
        </aside>
      </section>}
      {completedSale && (
        <div className="receipt-backdrop" role="dialog" aria-modal="true" aria-labelledby="receipt-title">
          <div className="receipt-modal">
            <div className="receipt-actions">
              <span>Sale completed. Print or close this receipt.</span>
              <button type="button" className="secondary-button" onClick={() => window.print()}><Printer size={16} /> Print receipt</button>
              <button type="button" className="primary-button" onClick={() => setCompletedSale(null)}>Done</button>
            </div>
            <article className="print-receipt">
              <header>
                <h2 id="receipt-title">URBAN LIQUOR LITEIN</h2>
                <p>SALES RECEIPT</p>
              </header>
              <div className="receipt-meta">
                <p>Receipt: <b>#{completedSale.id}</b></p>
                <p>{formatReceiptDate(completedSale.created_at)}</p>
              </div>
              <table>
                <thead><tr><th>Item</th><th>Qty</th><th>Total</th></tr></thead>
                <tbody>
                  {completedSale.items.map((item) => (
                    <tr key={item.id}>
                      <td>{item.product_name}<small>{item.sku} · {money(item.unit_price)} each</small></td>
                      <td>{item.quantity}</td>
                      <td>{money(item.line_total)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="receipt-total">
                <p><span>Subtotal</span><b>{money(completedSale.subtotal)}</b></p>
                <p className="receipt-grand-total"><span>Total</span><b>{money(completedSale.total)}</b></p>
              </div>
              <div className="receipt-payments">
                <b>Payment</b>
                {completedSale.payments.map((payment) => (
                  <p key={payment.id}>
                    <span>{payment.method === "mpesa" ? "M-Pesa" : "Cash"}</span>
                    <b>{money(payment.amount)}</b>
                    {payment.method === "cash" && Number(payment.cash_received) > 0 && <small>Received {money(payment.cash_received)} · Change {money(payment.change_given)}</small>}
                    {payment.mpesa_reference && <small>M-Pesa ref: {payment.mpesa_reference}</small>}
                  </p>
                ))}
              </div>
              <footer>Thank you for shopping with us.</footer>
            </article>
          </div>
        </div>
      )}
      {completedWholesaleSale && (
        <div className="receipt-backdrop" role="dialog" aria-modal="true" aria-labelledby="wholesale-invoice-title">
          <div className="receipt-modal">
            <div className="receipt-actions">
              <span>Wholesale delivery recorded. Print or close this invoice.</span>
              <button type="button" className="secondary-button" onClick={() => window.print()}><Printer size={16} /> Print invoice</button>
              <button type="button" className="primary-button" onClick={() => setCompletedWholesaleSale(null)}>Done</button>
            </div>
            <article className="print-receipt">
              <header>
                <h2 id="wholesale-invoice-title">URBAN LIQUOR LITEIN</h2>
                <p>WHOLESALE INVOICE / DELIVERY NOTE</p>
              </header>
              <div className="receipt-meta">
                <p>Invoice: <b>#{completedWholesaleSale.id}</b></p>
                <p>{formatReceiptDate(completedWholesaleSale.created_at)}</p>
                <p>Shop: <b>{completedWholesaleSale.customer_name}</b></p>
                {completedWholesaleSale.delivery_reference && <p>Reference: <b>{completedWholesaleSale.delivery_reference}</b></p>}
                <p>Recorded by: <b>{completedWholesaleSale.created_by_name}</b></p>
              </div>
              <table className="wholesale-invoice-table">
                <thead><tr><th>Item</th><th>Qty</th><th>Price</th><th>Total</th></tr></thead>
                <tbody>
                  {completedWholesaleSale.items.map((item) => (
                    <tr key={item.id}>
                      <td>{item.product_name}<small>{item.sku}</small></td>
                      <td>{item.quantity}</td>
                      <td>{money(item.unit_price)}</td>
                      <td>{money(item.line_total)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="receipt-total">
                <p><span>Total</span><b>{money(completedWholesaleSale.total)}</b></p>
                <p><span>Paid</span><b>{money(completedWholesaleSale.amount_paid)}</b></p>
                <p className="receipt-grand-total"><span>Balance due</span><b>{money(completedWholesaleSale.balance_due)}</b></p>
              </div>
              <div className="receipt-payments">
                <b>Payment status: {completedWholesaleSale.payment_status}</b>
                {completedWholesaleSale.payments.map((payment) => (
                  <p key={payment.id}>
                    <span>{payment.method === "mpesa" ? "M-Pesa" : "Cash"}</span>
                    <b>{money(payment.amount)}</b>
                    {payment.mpesa_reference && <small>M-Pesa ref: {payment.mpesa_reference}</small>}
                  </p>
                ))}
              </div>
              <footer>Please retain this invoice for your records.</footer>
            </article>
          </div>
        </div>
      )}
    </main>
  );
}
