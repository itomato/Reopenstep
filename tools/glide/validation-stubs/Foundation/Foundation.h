#ifndef REOPENSTEP_VALIDATION_FOUNDATION_H
#define REOPENSTEP_VALIDATION_FOUNDATION_H

/* Only the selectors used by macosxglide.m; never linked or shipped. */
__attribute__((objc_root_class))
@interface NSAutoreleasePool
+ alloc;
- init;
- release;
@end

__attribute__((objc_root_class))
@interface NSString
- initWithCString:(const char *)value;
- (unsigned int)length;
- getCString:(char *)buffer;
- release;
@end

__attribute__((objc_root_class))
@interface NSUserDefaults
+ standardUserDefaults;
- (NSString *)stringForKey:(NSString *)key;
@end

#endif
