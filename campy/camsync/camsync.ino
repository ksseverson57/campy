int DIG_out_pins[] = {2, 4, 7, 8, 12, 13}; // 3, 5, 6, 9, 10, 11 = PWM
int n_sync = 1;
long frame_rate = 1; // fps
long frame_period = 1000 / frame_rate * 1000;
long pulse_duration = frame_period / 2;
long frame_start = 0;
int DIG_level = LOW;

void setup( void )
{
  n_sync = int( sizeof(DIG_out_pins) / sizeof(int) );
  for ( byte i = 0; i < n_sync; i++ ) 
  {
    pinMode(DIG_out_pins[i], OUTPUT);
    digitalWrite(DIG_out_pins[i], LOW);
  }
  
  Serial.begin(115200);

  // Wait to receive data from Python...
  Serial.setTimeout(1000);
  while ( true )
  {
    if (Serial.available() > 0)
    {
      frame_rate = Serial.parseInt();
      Serial.println(frame_rate);
      frame_period = 1000 / frame_rate * 1000; // microseconds
      pulse_duration = frame_period / 2;
      Serial.println(frame_period);
      Serial.println(pulse_duration);
      delay(1000);
      break;
    }
  }
  delay(5000); // Wait n ms for streams and cams to initialize
}

void loop( void ) 
{ 
  frame_start = micros();
  for ( byte i = 0; i < n_sync; i++ ) 
  {
    digitalWrite(DIG_out_pins[i], HIGH);
  }
  
  while ((micros() - frame_start) <= pulse_duration)
  {} // just wait
  
  for ( byte i = 0; i < n_sync; i++ ) 
  {
    digitalWrite(DIG_out_pins[i], LOW);
  }
  
  while ((micros() - frame_start) < frame_period)
  {} // wait for it...
}
