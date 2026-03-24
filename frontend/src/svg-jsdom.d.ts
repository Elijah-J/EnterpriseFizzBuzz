/**
 * jsdom does not implement SVGGeometryElement methods on the correct prototype.
 * Tests polyfill them on SVGElement.prototype. This declaration allows those
 * assignments to type-check.
 */
interface SVGElement {
  getTotalLength(): number;
  getPointAtLength(distance: number): DOMPoint;
}
