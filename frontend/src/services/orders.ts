import { DEMO_MODE } from './auth';
import { editorialImages, formatVND } from './catalog';

export type OrderItem = { id: number; product_id: string; product_name: string | null; image_url: string | null; thumb_url?: string | null; quantity: number; unit_price: number; subtotal: number };
export type Order = { id: number; user_id: string; total_amount: number; status: string; created_at: string | null; items: OrderItem[] };
const API_URL = (import.meta.env.VITE_ORDER_API_URL || import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
const demoItems = [
  {id:1,product_id:'DEMO-G02',product_name:'Ivory Electric Guitar',image_url:editorialImages.electric,thumb_url:null,quantity:1,unit_price:9750000,subtotal:9750000},
  {id:2,product_id:'DEMO-S01',product_name:'Home Studio Accessories',image_url:editorialImages.studio,thumb_url:null,quantity:1,unit_price:350000,subtotal:350000},
  {id:3,product_id:'DEMO-K01',product_name:'Essential 61 Keyboard',image_url:editorialImages.keys,thumb_url:null,quantity:1,unit_price:6400000,subtotal:6400000},
  {id:4,product_id:'DEMO-HDP',product_name:'Studio Monitor Headphones',image_url:editorialImages.studio,thumb_url:null,quantity:1,unit_price:2850000,subtotal:2850000},
];
export async function getOrders(token: string, userId: string): Promise<Order[]> {
  if (DEMO_MODE) return [
    {id:10428,user_id:userId,total_amount:10100000,status:'CONFIRMED',created_at:'2026-11-18T10:30:00Z',items:demoItems.slice(0,2)},
    {id:10396,user_id:userId,total_amount:6400000,status:'DELIVERED',created_at:'2026-11-02T12:20:00Z',items:[demoItems[2]]},
    {id:10281,user_id:userId,total_amount:2850000,status:'DELIVERED',created_at:'2026-10-11T08:40:00Z',items:[demoItems[3]]},
  ];
  let response: Response;
  try { response = await fetch(`${API_URL}/api/v1/orders`, { headers: { Authorization: `Bearer ${token}` } }); }
  catch { throw new Error('Cannot reach the order service. Check VITE_ORDER_API_URL and that the backend is running.'); }
  if (!response.ok) throw new Error(`Unable to fetch orders (${response.status}).`);
  return await response.json() as Order[];
}
export const formatMoney = formatVND;
export const formatDate = (iso: string | null) => iso ? new Date(iso).toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'}) : 'Date unavailable';
