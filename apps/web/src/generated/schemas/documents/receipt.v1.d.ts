/* Generated from schemas/ by make gen-schemas. Do not edit. */

/**
 * Proof of a payment already made, such as a till slip.
 */
export interface Receipt {
  /**
   * Receipt or bill number.
   */
  receipt_number: string | null;
  /**
   * Date of payment (YYYY-MM-DD).
   */
  date: string | null;
  /**
   * Time of payment, 24-hour HH:MM.
   */
  time: string | null;
  /**
   * The shop or business that was paid.
   */
  merchant: Party | null;
  /**
   * ISO 4217 code, e.g. INR.
   */
  currency: string | null;
  /**
   * Each purchased line, in order.
   */
  line_items: {
    /**
     * What was bought.
     */
    description: string | null;
    /**
     * Quantity.
     */
    quantity: number | null;
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
   * Total tax.
   */
  tax_total: Money | null;
  /**
   * Amount paid.
   */
  total: Money | null;
  /**
   * How it was paid, e.g. cash, card, UPI.
   */
  payment_method: string | null;
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
