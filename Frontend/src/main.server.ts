import { bootstrapApplication } from '@angular/platform-browser';
import { AppComponent } from './app/app.component';
import { provideHttpClient } from '@angular/common/http';

export default function () {
  return bootstrapApplication(AppComponent, {
    providers: [provideHttpClient()]
  });
}