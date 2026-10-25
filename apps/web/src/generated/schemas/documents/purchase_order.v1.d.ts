/* Generated from schemas/ by make gen-schemas. Do not edit. */

/**
 * A buyer's order to a supplier.
 */
export interface PurchaseOrder {
  /**
   * Purchase order number.
   */
  po_number: string | null;
  /**
   * Order date (YYYY-MM-DD).
   */
  po_date: string | null;
  /**
   * Requested delivery date (YYYY-MM-DD).
   */
  delivery_date: string | null;
  /**
   * The company placing the order.
   */
  buyer: Party | null;
  /**
   * The supplier.
   */
  vendor: Party | null;
  /**
   * ISO 4217 code, e.g. INR.
   */
  currency: string | null;
  /**
   * Each ordered line, in order.
   */
  line_items: {
    /**
     * What was sold.
     */
    description: string | null;
    /**
     * HSN or SAC code.
     */
    hsn_sac: string | null;
    /**
     * Quantity.
     */
    quantity: number | null;
    /**
     * Price per unit.
     */
    unit_price: Money | null;
    /**
     * Line total.
     */
    amount: Money | null;
  }[];
  /**
   * Total before tax.
   */
  subtotal: Money | null;
  /**
   * Each tax line.
   */
  taxes: {
    /**
     * Tax kind, or null if not stated.
     */
    type: ("CGST" | "SGST" | "IGST" | "CESS" | "OTHER") | null;
    /**
     * Rate in percent, e.g. 9 for 9%.
     */
    rate_percent: number | null;
    /**
     * Tax amount.
     */
    amount: Money | null;
  }[];
  /**
   * Order total.
   */
  total: Money | null;
}
/**
 * A seller, buyer or merchant.
 */
export interface Party {
  /**
   * Legal or trading name.
   */
  name: string | null;
  /**
   * 15-character Indian GSTIN, or null if absent.
   */
  gstin: string | null;
  /**
   * Postal address, or null if absent.
   */
  address: Address | null;
}
export interface Address {
  /**
   * First address line.
   */
  line1: string | null;
  /**
   * Second address line.
   */
  line2: string | null;
  /**
   * City.
   */
  city: string | null;
  /**
   * State or province.
   */
  state: string | null;
  /**
   * PIN or postal code.
   */
  postal_code: string | null;
  /**
   * Country.
   */
  country: string | null;
}
/**
 * An amount as printed, with its currency.
 */
export interface Money {
  /**
   * The amount as a number, without currency symbols or thousands separators.
   */
  amount: number | null;
  /**
   * ISO 4217 code, e.g. INR.
   */
  currency: string | null;
}
