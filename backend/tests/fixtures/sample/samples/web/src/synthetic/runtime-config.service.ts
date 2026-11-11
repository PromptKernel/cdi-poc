// SYNTHETIC: added for the cross-layer dependency graph PoC; not part of the MIT base sample.
import { Injectable } from '@angular/core';

@Injectable({ providedIn: 'root' })
export class RuntimeConfigService {
  private values: { [key: string]: string } = {};

  // Loaded at runtime from assets/config.json (not statically resolvable).
  load(json: { [key: string]: string }) {
    this.values = json;
  }

  get(key: string): string {
    return this.values[key];
  }
}
