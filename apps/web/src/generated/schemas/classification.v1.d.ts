/* Generated from schemas/ by make gen-schemas. Do not edit. */

/**
 * What kind of document this is, and how sure the model is.
 */
export interface Classification {
  /**
   * invoice, receipt, purchase_order, or other for anything else.
   */
  doc_type: "invoice" | "receipt" | "purchase_order" | "other";
  /**
   * Probability from 0 to 1 that doc_type is correct.
   */
  confidence: number;
}
