import { Component, ViewChild, AfterViewInit } from '@angular/core';
import { ChatComponent } from './chat/chat.component';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [ChatComponent],
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.css']  
})
export class AppComponent implements AfterViewInit {
  @ViewChild(ChatComponent) chatComponent!: ChatComponent;

  ngAfterViewInit() {
    setTimeout(() => {}, 0);
  }

  openChat() {
    if (this.chatComponent && !this.chatComponent.isChatOpen) {
      this.chatComponent.toggleChat();
    }
  }
}