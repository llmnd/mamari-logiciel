export interface StoreProduct {
  id: string;
  name: string;
  description: string | null;
  category: string | null;
  unit: string;
  price_fcfa: number;
  stock_quantity: number;
  is_published: boolean;
  is_active: boolean;
  photo_url: string | null;
  created_at: string;
  updated_at: string;
}

export interface StoreProductPage {
  organization_name: string;
  items: StoreProduct[];
}

export interface StoreOrder {
  id: string;
  reference: string;
  customer_name: string;
  customer_phone: string | null;
  customer_email: string | null;
  delivery_address: string | null;
  delivery_latitude: number | null;
  delivery_longitude: number | null;
  delivery_distance_km: number | null;
  delivery_fee_fcfa: number | null;
  delivery_quote_required: boolean;
  order_date: string;
  amount_fcfa: number;
  status: "pending" | "confirmed" | "preparing" | "delivered" | "cancelled";
  created_at: string;
  items: {
    product_id: string | null;
    product_name: string;
    unit: string;
    quantity: number;
    unit_price_fcfa: number;
  }[];
}

export interface StoreCustomerProfile {
  full_name: string;
  email: string;
  phone: string;
  address: string | null;
}

export interface StoreOrderSummary {
  in_progress_count: number;
  delivered_count: number;
  total_spent_fcfa: number;
}

export interface StoreOrderNotification {
  order_id: string;
  order_reference: string;
  status: StoreOrder["status"];
  created_at: string;
}
