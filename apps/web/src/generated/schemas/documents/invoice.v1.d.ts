/* Generated from schemas/ by make gen-schemas. Do not edit. */

/**
 * A tax invoice or bill from a seller.
 */
export interface Invoice {
  /**
   * Invoice number as printed.
   */
  invoice_number: string | null;
  /**
   * Invoice date (YYYY-MM-DD).
   */
  invoice_date: string | null;
  /**
   * Payment due date (YYYY-MM-DD).
   */
  due_date: string | null;
  /**
   * The seller who issued the invoice.
   */
  vendor: Party | null;
  /**
   * The customer billed.
   */
  buyer: Party | null;
  /**
   * GST place of supply (state).
   */
  place_of_supply: string | null;
  /**
   * ISO 4217 code, e.g. INR.
   */
  currency: string | null;
  /**
   * Each billed line, in order.
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
   * Each tax line (CGST, SGST, IGST…).
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
   * Grand total payable.
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
