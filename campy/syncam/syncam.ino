int DIG_out_pins[] = {2, 4, 7, 8, 12, 13}; // 3, 5, 6, 9, 10, 11 = PWM
int n_sync = 1;
unsigned long frame_rate = 0;
unsigned long frame_period, pulse_duration; // fps

void setup( void )
{
  n_sync = int( sizeof(DIG_out_pins) / sizeof(int) );
  for ( byte i = 0; i < n_sync; i++ ) 
  {
    pinMode(DIG_out_pins[i], OUTPUT);
    digitalWrite(DIG_out_pins[i], LOW);
  }
  
  Serial.begin(115200);
  Serial.println("Set baudrate to 115200.");
  Serial.println("Enter your frame rate:");
  
  // Wait to receive data from Python or Serial Monitor...
  while (Serial.available() == 0) {}

  frame_rate = Serial.parseInt();
  Serial.println(frame_rate);
  if (frame_rate == 0) { // Avoid divide-by-zero error
    frame_period = 0xFFFFFFFF;
    pulse_duration = 0xFFFFFFFF;
  }
  else {
    frame_period = 1e6 / frame_rate; // microseconds
    pulse_duration = frame_period / 2; // ~50% duty cycle
  }
  Serial.println(frame_period);
  Serial.println(pulse_duration);
  delay(4000); // Wait n ms for streams and cams to initialize
}

void loop( void ) {
  // Stay on lookout for pyserial com
  // If message sent, stop triggers
  if (Serial.available() == 1) {
    frame_period = 0xFFFFFFFF;
    pulse_duration = 0xFFFFFFFF;
  }

  noInterrupts();
  unsigned long frame_start = micros();
  for ( byte i = 0; i < n_sync; i++ ) {
    digitalWrite(DIG_out_pins[i], HIGH); 
  }
  interrupts();
  
  while ((micros() - frame_start) < pulse_duration) {
  } // wait 

  noInterrupts();
  for ( byte i = 0; i < n_sync; i++ ) {
    digitalWrite(DIG_out_pins[i], LOW); 
  }
  interrupts();
  
  while ((micros() - frame_start) < frame_period) {
  } // wait
}
