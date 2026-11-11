import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowDownLeft,
  ArrowRight,
  BadgeCheck,
  Banknote,
  Check,
  CircleAlert,
  LoaderCircle,
  LogOut,
  Minus,
  Plus,
  Search,
  ShieldCheck,
  ShoppingBag,
  Smartphone,
  Wine,
  X,
} from "lucide-react";

const API_URL = (import.meta.env.VITE_API_URL || "/api/v1").replace(/\/$/, "");
const CURRENCY = "KES";

type Staff = {
  id: number;
  email: string;
  full_name: string;
  role: "owner" | "cashier";
};

type Product = {
  id: number;
  sku: string;
  barcode: string | null;
  name: string;
  category: string | null;
  unit_price: string;
  stock_quantity: string;
  low_stock_threshold: string;
};

type Sale = {
  id: number;
  total: string;
  currency: string;
  payments: { method: string; amount: string; change_given: string }[];
};

type CartLine = { product: Product; quantity: number };

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

export default function App() {
  const [token, setToken] = useState(() => sessionStorage.getItem("urban-pos-token") || "");
  const [staff, setStaff] = useState<Staff | null>(null);
  const [products, setProducts] = useState<Product[]>([]);
  const [cart, setCart] = useState<CartLine[]>([]);
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
    setNotice("");
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
      [product.name, product.sku, product.barcode || ""].some((value) =>
        value.toLowerCase().includes(query),
      ),
    );
  }, [products, search]);

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
          email: form.get("email"),
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
          <div className="brand brand-light"><span className="brand-mark"><Wine size={20} /></span> URBAN LIQUOR</div>
          <div className="aside-copy">
            <span className="eyebrow">STORE OPERATIONS</span>
            <h1>Good service.<br />Smooth checkout.</h1>
            <p>Your counter, inventory, and daily sales—together in one place.</p>
          </div>
          <div className="aside-foot"><ShieldCheck size={16} /> Staff access only</div>
        </section>
        <section className="login-panel">
          <div className="login-card">
            <div className="mobile-brand brand"><span className="brand-mark"><Wine size={20} /></span> URBAN LIQUOR</div>
            <span className="eyebrow">WELCOME BACK</span>
            <h2>Sign in to your store</h2>
            <p className="muted">Use your staff account to open the point of sale.</p>
            <form onSubmit={submitLogin} className="login-form">
              <label htmlFor="email">Email address</label>
              <input id="email" name="email" type="email" autoComplete="username" placeholder="you@yourstore.co.ke" required />
              <label htmlFor="password">Password</label>
              <input id="password" name="password" type="password" autoComplete="current-password" placeholder="Enter your password" required />
              {error && <div className="alert error"><CircleAlert size={16} />{error}</div>}
              <button className="primary-button login-submit" disabled={busy}>
                {busy ? <LoaderCircle className="spin" size={18} /> : <>Sign in <ArrowRight size={17} /></>}
              </button>
            </form>
            <div className="login-note"><ShieldCheck size={16} /> Your account is managed by your store owner.</div>
          </div>
          <footer>Urban Liquor POS <span>•</span> Secure staff sign-in</footer>
        </section>
      </main>
    );
  }

  return (
    <main className="pos-shell">
      <header className="topbar">
        <div className="brand"><span className="brand-mark"><Wine size={20} /></span> URBAN LIQUOR</div>
        <div className="topbar-right">
          <div className="staff-chip"><span className="avatar">{staff.full_name.slice(0, 1).toUpperCase()}</span><span><b>{staff.full_name}</b><small>{staff.role}</small></span></div>
          <button className="icon-button" onClick={logout} aria-label="Sign out" title="Sign out"><LogOut size={18} /></button>
        </div>
      </header>
      <section className="workspace">
        <div className="catalog">
          <div className="page-heading">
            <div><span className="eyebrow">POINT OF SALE</span><h1>Checkout</h1><p className="muted">Find a product or scan its barcode to add it to the sale.</p></div>
            <div className="product-count"><Wine size={17} /> {products.length} products</div>
          </div>
          <label className="search-box"><Search size={18} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search name, SKU, or barcode..." /><kbd>⌕</kbd></label>
          <div className="product-grid">
            {filteredProducts.map((product) => {
              const stock = Number(product.stock_quantity);
              const low = stock <= Number(product.low_stock_threshold);
              return (
                <button className="product-card" key={product.id} onClick={() => addToCart(product)} disabled={stock <= 0}>
                  <div className="product-art"><Wine size={24} /><span>{product.category || "BOTTLE"}</span></div>
                  <div className="product-info"><small>{product.sku}</small><b>{product.name}</b><div className="product-meta"><strong>{money(product.unit_price)}</strong><span className={low ? "stock low" : "stock"}>{stock} in stock</span></div></div>
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
      </section>
    </main>
  );
}
