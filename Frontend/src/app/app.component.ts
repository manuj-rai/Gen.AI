import { Component } from '@angular/core';
import { ChatComponent } from './chat/chat.component';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [ChatComponent],
  template: `
    <div class="h-screen w-screen bg-gray-100 dark:bg-gray-900">
      <app-chat></app-chat>
    </div>
  `
})
export class AppComponent {}